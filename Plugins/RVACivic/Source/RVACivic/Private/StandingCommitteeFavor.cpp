#include "StandingCommitteeFavor.h"

#include "StandingCommitteeSkeleton.h"
#include "Components/ChildActorComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
using RVA::StandingCommittee::Stage;

static_assert(static_cast<uint8>(Stage::Available) == static_cast<uint8>(EStandingCommitteeFavorStage::Available));
static_assert(static_cast<uint8>(Stage::Borrowed) == static_cast<uint8>(EStandingCommitteeFavorStage::Borrowed));
static_assert(static_cast<uint8>(Stage::Returned) == static_cast<uint8>(EStandingCommitteeFavorStage::Returned));
}

AStandingCommitteeHandTruck::AStandingCommitteeHandTruck()
{
    PrimaryActorTick.bCanEverTick = false;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("HandTruckBase")));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));

    const auto MakePart = [this](FName Name, UStaticMesh* Shape, const FVector& Position, const FVector& Size,
        const FRotator& Rotation = FRotator::ZeroRotator)
    {
        UStaticMeshComponent* Part = CreateDefaultSubobject<UStaticMeshComponent>(Name);
        Part->SetupAttachment(GetRootComponent());
        Part->SetStaticMesh(Shape);
        Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Part->SetRelativeLocation(Position);
        Part->SetRelativeRotation(Rotation);
        Part->SetRelativeScale3D(Size / 100.0);
    };

    MakePart(TEXT("ToePlate"), Cube.Object, FVector(14, 0, 8), FVector(33, 41, 4));
    MakePart(TEXT("LeftUpright"), Cube.Object, FVector(-4, -14, 53), FVector(5, 5, 91));
    MakePart(TEXT("RightUpright"), Cube.Object, FVector(-4, 14, 53), FVector(5, 5, 91));
    MakePart(TEXT("Handle"), Cube.Object, FVector(-5, 0, 99), FVector(7, 39, 7));
    MakePart(TEXT("Brace"), Cube.Object, FVector(-4, 0, 44), FVector(4, 31, 5));
    MakePart(TEXT("LeftWheel"), Cylinder.Object, FVector(-7, -20, 12), FVector(24, 24, 9), FRotator(0, 0, 90));
    MakePart(TEXT("RightWheel"), Cylinder.Object, FVector(-7, 20, 12), FVector(24, 24, 9), FRotator(0, 0, 90));
}

AStandingCommitteeFavor::AStandingCommitteeFavor()
{
    PrimaryActorTick.bCanEverTick = false;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("FavorOrigin")));
    PickupSite = CreateDefaultSubobject<USceneComponent>(TEXT("LoanSite"));
    PickupSite->SetupAttachment(GetRootComponent());
    ReturnSite = CreateDefaultSubobject<USceneComponent>(TEXT("ReturnSite"));
    ReturnSite->SetupAttachment(GetRootComponent());
    ReturnSite->SetRelativeLocation(FVector(2800, 0, 0));

    const auto Configure = [](USceneComponent& Site, UChildActorComponent& Skeleton,
        USphereComponent& Zone, UTextRenderComponent& Prompt)
    {
        Skeleton.SetupAttachment(&Site);
        Skeleton.SetChildActorClass(AStandingCommitteeSkeleton::StaticClass());
        Skeleton.SetRelativeLocation(FVector(0, 220, 0));
        Zone.SetupAttachment(&Site);
        Zone.SetRelativeLocation(FVector(0, 0, 82));
        Zone.InitSphereRadius(120.0f);
        Zone.SetCollisionObjectType(ECC_WorldDynamic);
        Zone.SetCollisionEnabled(ECollisionEnabled::QueryOnly);
        Zone.SetCollisionResponseToAllChannels(ECR_Ignore);
        Zone.SetCollisionResponseToChannel(ECC_Pawn, ECR_Overlap);
        Zone.SetGenerateOverlapEvents(true);
        Prompt.SetupAttachment(&Site);
        Prompt.SetRelativeLocation(FVector(0, 0, 140));
        Prompt.SetHorizontalAlignment(EHTA_Center);
        Prompt.SetWorldSize(25.0f);
    };

    PickupSkeleton = CreateDefaultSubobject<UChildActorComponent>(TEXT("BareSkeleton"));
    PickupZone = CreateDefaultSubobject<USphereComponent>(TEXT("LoanZone"));
    PickupPrompt = CreateDefaultSubobject<UTextRenderComponent>(TEXT("LoanPrompt"));
    Configure(*PickupSite, *PickupSkeleton, *PickupZone, *PickupPrompt);

    ReturnSkeleton = CreateDefaultSubobject<UChildActorComponent>(TEXT("VestSkeleton"));
    ReturnZone = CreateDefaultSubobject<USphereComponent>(TEXT("ReturnZone"));
    ReturnPrompt = CreateDefaultSubobject<UTextRenderComponent>(TEXT("ReturnPrompt"));
    Configure(*ReturnSite, *ReturnSkeleton, *ReturnZone, *ReturnPrompt);

    PickupZone->OnComponentBeginOverlap.AddDynamic(this, &AStandingCommitteeFavor::HandlePickupOverlap);
    ReturnZone->OnComponentBeginOverlap.AddDynamic(this, &AStandingCommitteeFavor::HandleReturnOverlap);
}

void AStandingCommitteeFavor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    ApplySignals();
    RefreshPrompts();
}

void AStandingCommitteeFavor::BeginPlay()
{
    Super::BeginPlay();
    ApplySignals();
    if (!HasAuthority())
    {
        return;
    }

    FActorSpawnParameters Spawn;
    Spawn.Owner = this;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    HandTruck = GetWorld()->SpawnActor<AStandingCommitteeHandTruck>(
        PickupSite->GetComponentLocation(), PickupSite->GetComponentRotation(), Spawn);
    RefreshPrompts();

    // Overlaps registered before the truck spawned still count.
    TArray<AActor*> AtPickup;
    PickupZone->GetOverlappingActors(AtPickup, ACharacter::StaticClass());
    for (AActor* Actor : AtPickup)
    {
        if (ACharacter* Character = Cast<ACharacter>(Actor))
        {
            TryBorrow(*Character);
        }
    }
}

void AStandingCommitteeFavor::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (ACharacter* Character = Borrower.Get())
    {
        Character->OnDestroyed.RemoveDynamic(this, &AStandingCommitteeFavor::HandleBorrowerDestroyed);
    }
    if (IsValid(HandTruck.Get()))
    {
        HandTruck->Destroy();
    }
    Super::EndPlay(EndPlayReason);
}

EStandingCommitteeFavorStage AStandingCommitteeFavor::GetStage() const
{
    return static_cast<EStandingCommitteeFavorStage>(Progress.GetStage());
}

FText AStandingCommitteeFavor::GetObjective() const
{
    switch (Progress.GetStage())
    {
        case Stage::Borrowed:
            return NSLOCTEXT("StandingCommittee", "ReturnAtVest", "Return the hand truck to the skeleton in the safety vest.");
        case Stage::Returned:
            return NSLOCTEXT("StandingCommittee", "LoanReturned", "Hand truck returned.");
        default:
            return NSLOCTEXT("StandingCommittee", "TakeHandTruck", "Borrow the hand truck.");
    }
}

void AStandingCommitteeFavor::ApplySignals()
{
    if (AStandingCommitteeSkeleton* Skeleton = Cast<AStandingCommitteeSkeleton>(PickupSkeleton->GetChildActor()))
    {
        Skeleton->SetSignal(EStandingCommitteeSignal::Bare);
    }
    if (AStandingCommitteeSkeleton* Skeleton = Cast<AStandingCommitteeSkeleton>(ReturnSkeleton->GetChildActor()))
    {
        Skeleton->SetSignal(EStandingCommitteeSignal::SafetyVest);
    }
}

void AStandingCommitteeFavor::RefreshPrompts()
{
    PickupPrompt->SetText(Progress.GetStage() == Stage::Borrowed
        ? NSLOCTEXT("StandingCommittee", "BorrowedLabel", "Return it to the skeleton in the safety vest")
        : NSLOCTEXT("StandingCommittee", "PickupLabel", "Hand truck to borrow"));
    PickupPrompt->SetHiddenInGame(Progress.GetStage() == Stage::Returned);
    ReturnPrompt->SetText(Progress.GetStage() == Stage::Returned
        ? NSLOCTEXT("StandingCommittee", "CompleteLabel", "Thanks for bringing it back.")
        : NSLOCTEXT("StandingCommittee", "DropoffLabel", "Hand truck return"));
    ReturnPrompt->SetHiddenInGame(Progress.GetStage() == Stage::Available);
}

void AStandingCommitteeFavor::NotifyStage()
{
    RefreshPrompts();
    OnFavorChanged.Broadcast(GetStage(), GetObjective());
}

void AStandingCommitteeFavor::TryBorrow(ACharacter& Character)
{
    if (!HasAuthority() || !Character.IsPlayerControlled() || !Character.GetRootComponent()
        || !IsValid(HandTruck.Get()) || Progress.GetStage() != Stage::Available)
    {
        return;
    }
    if (!HandTruck->AttachToComponent(Character.GetRootComponent(), FAttachmentTransformRules::SnapToTargetNotIncludingScale))
    {
        return;
    }
    HandTruck->GetRootComponent()->SetRelativeLocationAndRotation(FVector(50, 31, -80), FRotator(12, 0, 0));
    Progress.Borrow();
    Borrower = &Character;
    Character.OnDestroyed.AddUniqueDynamic(this, &AStandingCommitteeFavor::HandleBorrowerDestroyed);
    NotifyStage();
}

void AStandingCommitteeFavor::TryReturn(ACharacter& Character)
{
    if (!HasAuthority() || Borrower.Get() != &Character || !Character.IsPlayerControlled()
        || !IsValid(HandTruck.Get()) || !Progress.Return())
    {
        return;
    }
    Character.OnDestroyed.RemoveDynamic(this, &AStandingCommitteeFavor::HandleBorrowerDestroyed);
    Borrower.Reset();
    ParkTruck(*ReturnSite);
    if (IsValid(CourtyardGate.Get()) && CourtyardGate.Get() != this)
    {
        CourtyardGate->SetActorEnableCollision(false);
        CourtyardGate->SetActorHiddenInGame(true);
    }
    NotifyStage();
}

void AStandingCommitteeFavor::ParkTruck(const USceneComponent& Site)
{
    if (!IsValid(HandTruck.Get()))
    {
        return;
    }
    HandTruck->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
    HandTruck->SetActorLocationAndRotation(Site.GetComponentLocation(), Site.GetComponentRotation(),
        false, nullptr, ETeleportType::TeleportPhysics);
}

void AStandingCommitteeFavor::HandlePickupOverlap(UPrimitiveComponent*, AActor* OtherActor,
    UPrimitiveComponent*, int32, bool, const FHitResult&)
{
    if (ACharacter* Character = Cast<ACharacter>(OtherActor))
    {
        TryBorrow(*Character);
    }
}

void AStandingCommitteeFavor::HandleReturnOverlap(UPrimitiveComponent*, AActor* OtherActor,
    UPrimitiveComponent*, int32, bool, const FHitResult&)
{
    if (ACharacter* Character = Cast<ACharacter>(OtherActor))
    {
        TryReturn(*Character);
    }
}

void AStandingCommitteeFavor::HandleBorrowerDestroyed(AActor*)
{
    if (!Progress.LoseBorrower())
    {
        return;
    }
    Borrower.Reset();
    ParkTruck(*PickupSite);
    NotifyStage();
}
