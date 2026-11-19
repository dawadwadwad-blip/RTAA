#include "NightShiftWorkOrder.h"

#include "Components/BoxComponent.h"
#include "Components/InputComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PawnMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/Paths.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
using namespace RVA::NightShift;

constexpr int32 SaveVersion = 1;
static_assert(static_cast<uint8>(Phase::Available) == static_cast<uint8>(ENightShiftPhase::Available));
static_assert(static_cast<uint8>(Phase::Briefed) == static_cast<uint8>(ENightShiftPhase::Briefed));
static_assert(static_cast<uint8>(Phase::Striping) == static_cast<uint8>(ENightShiftPhase::Striping));
static_assert(static_cast<uint8>(Phase::Detour) == static_cast<uint8>(ENightShiftPhase::Detour));
static_assert(static_cast<uint8>(Phase::ReturnToYard) == static_cast<uint8>(ENightShiftPhase::ReturnToYard));
static_assert(static_cast<uint8>(Phase::Complete) == static_cast<uint8>(ENightShiftPhase::Complete));
static_assert(static_cast<uint8>(Exit::None) == static_cast<uint8>(ENightShiftExit::None));
static_assert(static_cast<uint8>(Exit::Detour) == static_cast<uint8>(ENightShiftExit::Detour));
static_assert(static_cast<uint8>(Exit::Recovery) == static_cast<uint8>(ENightShiftExit::Recovery));

bool ContainsPawn(const UBoxComponent& Zone, const APawn& Pawn)
{
    const FVector Local = Zone.GetComponentTransform().InverseTransformPosition(Pawn.GetActorLocation());
    const FVector Extent = Zone.GetUnscaledBoxExtent();
    return FMath::Abs(Local.X) <= Extent.X && FMath::Abs(Local.Y) <= Extent.Y && FMath::Abs(Local.Z) <= Extent.Z;
}

void TintMesh(UStaticMeshComponent& Mesh, const FLinearColor& Color)
{
    UMaterialInstanceDynamic* Material = Cast<UMaterialInstanceDynamic>(Mesh.GetMaterial(0));
    if (!Material)
    {
        Material = Mesh.CreateDynamicMaterialInstance(0);
    }
    if (Material)
    {
        Material->SetVectorParameterValue(TEXT("Color"), Color);
    }
}
}

ANightShiftWorkOrder::ANightShiftWorkOrder()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickInterval = 0.05f;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("NightShiftOrigin")));

    const auto MakeZone = [this](FName Name, const FVector& Center, const FVector& Extent)
    {
        UBoxComponent* Box = CreateDefaultSubobject<UBoxComponent>(Name);
        Box->SetupAttachment(GetRootComponent());
        Box->SetRelativeLocation(Center);
        Box->InitBoxExtent(Extent);
        Box->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        return Box;
    };
    Yard = MakeZone(TEXT("Yard"), FVector(0, 0, 90), FVector(640, 450, 350));
    WorkZone = MakeZone(TEXT("AuthorizedWorkZone"), FVector(3300, 0, 120), FVector(1700, 680, 450));
    StripeA = MakeZone(TEXT("SegmentA"), FVector(2360, -100, 85), FVector(460, 200, 320));
    StripeB = MakeZone(TEXT("SegmentB"), FVector(3860, -100, 85), FVector(460, 200, 320));
    DetourExit = MakeZone(TEXT("DetourExit"), FVector(4300, 1220, 90), FVector(330, 270, 350));
    RecoveryExit = MakeZone(TEXT("RecoveryExit"), FVector(3130, -1220, 90), FVector(330, 270, 350));
    MainExitBarrier = MakeZone(TEXT("MainExitBarrier"), FVector(5060, 0, 85), FVector(39, 590, 85));
    MainExitBarrier->SetCollisionObjectType(ECC_WorldStatic);
    MainExitBarrier->SetCollisionResponseToAllChannels(ECR_Block);

    const auto MakeAnchor = [this](FName Name, const FVector& Location)
    {
        USceneComponent* Anchor = CreateDefaultSubobject<USceneComponent>(Name);
        Anchor->SetupAttachment(GetRootComponent());
        Anchor->SetRelativeLocation(Location);
        return Anchor;
    };
    WorkCheckpoint = MakeAnchor(TEXT("WorkCheckpoint"), FVector(1750, -100, 70));
    YardCheckpoint = MakeAnchor(TEXT("YardCheckpoint"), FVector(-170, 0, 70));

    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    const auto MakeMesh = [this](FName Name, USceneComponent& Attachment, UStaticMesh* Shape)
    {
        UStaticMeshComponent* Mesh = CreateDefaultSubobject<UStaticMeshComponent>(Name);
        Mesh->SetupAttachment(&Attachment);
        Mesh->SetStaticMesh(Shape);
        Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Mesh->SetGenerateOverlapEvents(false);
        return Mesh;
    };
    TestSurface = MakeMesh(TEXT("TestSurface"), *GetRootComponent(), Cube.Object);
    TestSurface->SetRelativeLocation(FVector(2700, 0, -25));
    TestSurface->SetRelativeScale3D(FVector(74, 36, 0.5));
    TestSurface->SetCollisionObjectType(ECC_WorldStatic);
    TestSurface->SetCollisionResponseToAllChannels(ECR_Block);
    BarrierMesh = MakeMesh(TEXT("BarrierMesh"), *MainExitBarrier, Cube.Object);
    PaintedA = MakeMesh(TEXT("PaintedA"), *StripeA, Cube.Object);
    PaintedB = MakeMesh(TEXT("PaintedB"), *StripeB, Cube.Object);
    PaintedA->SetRelativeLocation(FVector(0, 0, -83));
    PaintedB->SetRelativeLocation(FVector(0, 0, -83));
    PaintedA->SetCastShadow(false);
    PaintedB->SetCastShadow(false);

    ClosureLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("ClosureLight"));
    ClosureLight->SetupAttachment(MainExitBarrier);
    ClosureLight->SetRelativeLocation(FVector(320, 340, 290));
    ClosureLight->SetLightColor(FLinearColor(1.0f, 0.14f, 0.03f));
    ClosureLight->SetIntensity(20000.0f);
    ClosureLight->SetAttenuationRadius(1800.0f);
    ClosureLight->SetCastShadows(false);

    const auto MakeSign = [this](FName Name, USceneComponent& Attachment, const FVector& Position)
    {
        UTextRenderComponent* Sign = CreateDefaultSubobject<UTextRenderComponent>(Name);
        Sign->SetupAttachment(&Attachment);
        Sign->SetRelativeLocation(Position);
        Sign->SetRelativeRotation(FRotator(0, 180, 0));
        Sign->SetHorizontalAlignment(EHTA_Center);
        Sign->SetWorldSize(28.0f);
        return Sign;
    };
    ObjectiveSign = MakeSign(TEXT("YardObjective"), *Yard, FVector(140, 0, 155));
    WorkZoneSign = MakeSign(TEXT("WorkZoneIndicator"), *WorkZone, FVector(-1230, 320, 130));
    DetourSign = MakeSign(TEXT("DetourSign"), *DetourExit, FVector(0, 0, 125));
    RecoverySign = MakeSign(TEXT("RecoverySign"), *RecoveryExit, FVector(0, 0, 125));
    DetourSign->SetText(NSLOCTEXT("NightShift", "DetourSign", "DETOUR TO CITY YARD"));
    RecoverySign->SetText(NSLOCTEXT("NightShift", "RecoverySign", "ALTERNATE EXIT"));
}

void ANightShiftWorkOrder::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    RefreshWorld();
}

void ANightShiftWorkOrder::BeginPlay()
{
    Super::BeginPlay();
    if (HasAuthority())
    {
        LoadCheckpoint();
        BindTestKeys();
    }
    RefreshWorld();
}

void ANightShiftWorkOrder::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (APlayerController* Controller = TestController.Get())
    {
        DisableInput(Controller);
    }
    Super::EndPlay(EndPlayReason);
}

ENightShiftPhase ANightShiftWorkOrder::GetPhase() const
{
    return static_cast<ENightShiftPhase>(Order.GetCheckpoint().Current);
}

FText ANightShiftWorkOrder::GetObjective() const
{
    switch (Order.GetCheckpoint().Current)
    {
        case Phase::Available:
            return NSLOCTEXT("NightShift", "Briefing", "CITY YARD\nRead the overnight work order [E]");
        case Phase::Briefed:
            return NSLOCTEXT("NightShift", "BoardTruck", "WORK ORDER NS-01\nTake the city truck [E]");
        case Phase::Striping:
            return NSLOCTEXT("NightShift", "Paint", "OVERNIGHT STRIPING\nPaint both marked segments");
        case Phase::Detour:
            return NSLOCTEXT("NightShift", "Closed", "SCAFFOLD FIRE REPORTED\nClear the block by either marked exit");
        case Phase::ReturnToYard:
            return NSLOCTEXT("NightShift", "Debrief", "CITY YARD\nPark and submit the work order [E]");
        default:
            return Order.GetCheckpoint().Route == Exit::Detour
                ? NSLOCTEXT("NightShift", "FinishedDetour", "NIGHT SHIFT COMPLETE\nNS-01 dispatch filed\nTruck log recorded the detour")
                : NSLOCTEXT("NightShift", "FinishedRecovery", "NIGHT SHIFT COMPLETE\nNS-01 dispatch filed\nTruck log recorded the alternate exit");
    }
}

bool ANightShiftWorkOrder::GetEvidence(FNightShiftEvidence& OutEvidence) const
{
    OutEvidence = FNightShiftEvidence();
    if (Order.EvidenceCount() == 0)
    {
        return false;
    }
    const Exit Route = Order.GetCheckpoint().Route;
    OutEvidence.DispatchStub = FName(TEXT("NS-01.DispatchStub"));
    OutEvidence.LogEntry = FName(TEXT("NS-01.TruckExit"));
    OutEvidence.ExitTaken = static_cast<ENightShiftExit>(Route);
    OutEvidence.ExitLocation = TruckExitLocation;
    OutEvidence.TruckExitSeconds = TruckExitSeconds;
    return true;
}

bool ANightShiftWorkOrder::IsPlayerPawn(const APawn* Pawn) const
{
    if (!HasAuthority() || !IsValid(Pawn) || Pawn->GetWorld() != GetWorld())
    {
        return false;
    }
    const APlayerController* Controller = Cast<APlayerController>(Pawn->GetController());
    return Controller && Controller->IsLocalController() && Controller->GetPawn() == Pawn
        && (!OwnerController.IsValid() || OwnerController.Get() == Controller);
}

bool ANightShiftWorkOrder::IsWorkTruck(const APawn& Pawn) const
{
    return TruckTag != NAME_None && Pawn.ActorHasTag(TruckTag);
}

bool ANightShiftWorkOrder::PerformObjective(APawn* Pawn)
{
    if (!IsPlayerPawn(Pawn))
    {
        return false;
    }
    switch (Order.GetCheckpoint().Current)
    {
        case Phase::Available:
            if (!ContainsPawn(*Yard, *Pawn) || !Order.Brief())
            {
                return false;
            }
            OwnerController = Cast<APlayerController>(Pawn->GetController());
            break;
        case Phase::Briefed:
            if (!ContainsPawn(*Yard, *Pawn) || !IsWorkTruck(*Pawn) || !Order.BoardTruck())
            {
                return false;
            }
            break;
        case Phase::Striping:
            return IsWorkTruck(*Pawn) && StartStripe(*Pawn);
        case Phase::ReturnToYard:
            if (!ContainsPawn(*Yard, *Pawn) || !IsWorkTruck(*Pawn)
                || Pawn->GetVelocity().SizeSquared() > FMath::Square(100.0) || !Order.Debrief())
            {
                return false;
            }
            break;
        default:
            return false;
    }
    CommitProgress();
    return true;
}

bool ANightShiftWorkOrder::StartStripe(const APawn& Pawn)
{
    if (PaintingBit || !ContainsPawn(*WorkZone, Pawn))
    {
        return false;
    }
    for (Segment Candidate : {Segment::A, Segment::B})
    {
        const UBoxComponent& Zone = *(Candidate == Segment::A ? StripeA : StripeB);
        if (Order.HasStripe(Candidate) || !ContainsPawn(Zone, Pawn))
        {
            continue;
        }
        const FVector Local = Zone.GetComponentTransform().InverseTransformPosition(Pawn.GetActorLocation());
        if (ActivePass.Arm(Local.X / FMath::Max(1.0, Zone.GetUnscaledBoxExtent().X)))
        {
            PaintingBit = static_cast<uint8>(Candidate);
            RefreshWorld();
            return true;
        }
    }
    return false;
}

void ANightShiftWorkOrder::CancelStripe()
{
    PaintingBit = 0;
    ActivePass.Reset();
}

void ANightShiftWorkOrder::UpdateStripe(const APawn& Pawn)
{
    const Segment Target = static_cast<Segment>(PaintingBit);
    const UBoxComponent& Zone = *(Target == Segment::A ? StripeA : StripeB);
    const FVector Local = Zone.GetComponentTransform().InverseTransformPosition(Pawn.GetActorLocation());
    const FVector Extent = Zone.GetUnscaledBoxExtent();
    const bool bInsideLane = FMath::Abs(Local.Y) <= Extent.Y && FMath::Abs(Local.Z) <= Extent.Z;
    const PassStatus Result = ActivePass.Sample(Local.X / FMath::Max(1.0, Extent.X), bInsideLane, bInsideWorkZone);
    if (Result == PassStatus::Cancelled)
    {
        CancelStripe();
        RefreshWorld();
        return;
    }
    if (Result == PassStatus::Finished)
    {
        CancelStripe();
        if (Order.Paint(Target))
        {
            CommitProgress();
        }
    }
}

void ANightShiftWorkOrder::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!HasAuthority())
    {
        return;
    }
    BindTestKeys();
    APlayerController* Controller = OwnerController.Get();
    if (!Controller)
    {
        Controller = UGameplayStatics::GetPlayerController(this, 0);
    }
    APawn* Pawn = Controller ? Controller->GetPawn() : nullptr;
    const bool bTruckReady = IsPlayerPawn(Pawn) && IsWorkTruck(*Pawn);
    const Phase Current = Order.GetCheckpoint().Current;
    const bool bAuthorized = Current == Phase::Striping && bTruckReady && ContainsPawn(*WorkZone, *Pawn);
    if (bAuthorized != bInsideWorkZone)
    {
        bInsideWorkZone = bAuthorized;
        RefreshWorld();
    }
    if (PaintingBit)
    {
        if (bTruckReady)
        {
            UpdateStripe(*Pawn);
        }
        else
        {
            CancelStripe();
            RefreshWorld();
        }
    }
    if (Current == Phase::Detour && bTruckReady)
    {
        const Exit Route = ContainsPawn(*DetourExit, *Pawn) ? Exit::Detour
            : (ContainsPawn(*RecoveryExit, *Pawn) ? Exit::Recovery : Exit::None);
        if (Order.ClearSite(Route))
        {
            TruckExitLocation = Pawn->GetActorLocation();
            TruckExitSeconds = GetWorld()->GetTimeSeconds();
            CommitProgress();
        }
    }
}

void ANightShiftWorkOrder::CommitProgress()
{
    const Phase PreviousPhase = LastCheckpoint.Current;
    LastCheckpoint = Order.GetCheckpoint();
    const Phase NewPhase = LastCheckpoint.Current;
    if (NewPhase != Phase::Striping)
    {
        bInsideWorkZone = false;
    }
    SaveCheckpoint();
    RefreshWorld();
    OnProgressChanged.Broadcast(static_cast<ENightShiftPhase>(NewPhase));
    if (NewPhase == Phase::Detour && PreviousPhase == Phase::Striping)
    {
        OnClosure.Broadcast();
    }
    if (NewPhase == Phase::Complete && PreviousPhase == Phase::ReturnToYard)
    {
        OnDebriefCompleted.Broadcast();
    }
}

void ANightShiftWorkOrder::RefreshWorld()
{
    const Phase Current = Order.GetCheckpoint().Current;
    const bool bRoadClosed = Current == Phase::Detour || Current == Phase::ReturnToYard || Current == Phase::Complete;

    TestSurface->SetHiddenInGame(!bShowTestSurface);
    TestSurface->SetVisibility(bShowTestSurface);
    TestSurface->SetCollisionEnabled(bShowTestSurface ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
    MainExitBarrier->SetCollisionEnabled(bRoadClosed ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
    BarrierMesh->SetHiddenInGame(!bRoadClosed);
    BarrierMesh->SetVisibility(bRoadClosed);
    BarrierMesh->SetRelativeScale3D(MainExitBarrier->GetUnscaledBoxExtent() / 50.0);
    TintMesh(*BarrierMesh, FLinearColor(1.0f, 0.22f, 0.02f));

    const auto UpdateMark = [this](UStaticMeshComponent& Mesh, const UBoxComponent& Zone, Segment Which)
    {
        const FVector Extent = Zone.GetUnscaledBoxExtent();
        const bool bPainted = Order.HasStripe(Which);
        Mesh.SetRelativeScale3D(FVector(Extent.X / 50.0, bPainted ? 0.24 : 0.11, 0.035));
        TintMesh(Mesh, bPainted ? FLinearColor(0.10f, 0.76f, 0.38f)
            : FLinearColor(0.91f, 0.74f, 0.15f));
    };
    UpdateMark(*PaintedA, *StripeA, Segment::A);
    UpdateMark(*PaintedB, *StripeB, Segment::B);

    ClosureLight->SetVisibility(Current == Phase::Detour);
    ObjectiveSign->SetText(GetObjective());
    if (Current == Phase::Striping)
    {
        WorkZoneSign->SetText(!bInsideWorkZone
            ? NSLOCTEXT("NightShift", "OutsideZone", "WORK ORDER BOUNDARY\nEnter in the city truck")
            : (PaintingBit
                ? NSLOCTEXT("NightShift", "DriveToEnd", "LINE-STRIPER ACTIVE\nDrive to the far end")
                : NSLOCTEXT("NightShift", "ArmStriper", "AUTHORIZED ZONE\nPress E at either end of a yellow segment")));
    }
    else if (bRoadClosed)
    {
        WorkZoneSign->SetText(NSLOCTEXT("NightShift", "RouteClosed", "MAIN EXIT CLOSED\nUse a marked detour"));
    }
    else
    {
        WorkZoneSign->SetText(NSLOCTEXT("NightShift", "InactiveZone", "NIGHT WORK ZONE\nGet the work order at the yard"));
    }
    DetourSign->SetHiddenInGame(!bRoadClosed);
    RecoverySign->SetHiddenInGame(!bRoadClosed);
}

void ANightShiftWorkOrder::BindTestKeys()
{
    if (!bBindTestKeys || TestController.IsValid())
    {
        return;
    }
    APlayerController* Controller = UGameplayStatics::GetPlayerController(this, 0);
    if (!Controller || !Controller->IsLocalController())
    {
        return;
    }
    EnableInput(Controller);
    if (InputComponent)
    {
        TestController = Controller;
        if (!bKeysBound)
        {
            InputComponent->BindKey(EKeys::E, IE_Pressed, this, &ANightShiftWorkOrder::HandleObjectiveKey).bConsumeInput = false;
            InputComponent->BindKey(EKeys::R, IE_Pressed, this, &ANightShiftWorkOrder::HandleRetryKey).bConsumeInput = false;
            bKeysBound = true;
        }
    }
}

void ANightShiftWorkOrder::HandleObjectiveKey()
{
    if (APlayerController* Controller = TestController.Get())
    {
        PerformObjective(Controller->GetPawn());
    }
}

void ANightShiftWorkOrder::HandleRetryKey()
{
    if (APlayerController* Controller = TestController.Get())
    {
        RetryCheckpoint(Controller->GetPawn());
    }
}

FString ANightShiftWorkOrder::GetCheckpointSlot() const
{
    const FString Key = UGameplayStatics::GetCurrentLevelName(this, true) + TEXT("_") + CheckpointId.ToString();
    return TEXT("RVAA_NightShift_") + FPaths::MakeValidFileName(Key);
}

void ANightShiftWorkOrder::SaveCheckpoint()
{
    if (!bPersistCheckpoint)
    {
        return;
    }
    UNightShiftCheckpoint* Saved = Cast<UNightShiftCheckpoint>(
        UGameplayStatics::CreateSaveGameObject(UNightShiftCheckpoint::StaticClass()));
    if (!Saved)
    {
        return;
    }
    Saved->Version = SaveVersion;
    Saved->Phase = static_cast<uint8>(LastCheckpoint.Current);
    Saved->Stripes = LastCheckpoint.Stripes;
    Saved->Route = static_cast<uint8>(LastCheckpoint.Route);
    Saved->ExitLocation = TruckExitLocation;
    Saved->TruckExitSeconds = TruckExitSeconds;
    if (!UGameplayStatics::SaveGameToSlot(Saved, GetCheckpointSlot(), 0))
    {
        UE_LOG(LogTemp, Warning, TEXT("Night Shift disk checkpoint failed. In-session retry remains available."));
    }
}

void ANightShiftWorkOrder::LoadCheckpoint()
{
    if (!bPersistCheckpoint || !UGameplayStatics::DoesSaveGameExist(GetCheckpointSlot(), 0))
    {
        return;
    }
    const UNightShiftCheckpoint* Saved = Cast<UNightShiftCheckpoint>(
        UGameplayStatics::LoadGameFromSlot(GetCheckpointSlot(), 0));
    if (!Saved || Saved->Version != SaveVersion || Saved->ExitLocation.ContainsNaN()
        || !FMath::IsFinite(Saved->TruckExitSeconds) || Saved->TruckExitSeconds < 0.0
        || !Order.Restore({static_cast<Phase>(Saved->Phase), Saved->Stripes, static_cast<Exit>(Saved->Route)}))
    {
        UE_LOG(LogTemp, Warning, TEXT("Night Shift ignored an invalid or incompatible checkpoint."));
        return;
    }
    LastCheckpoint = Order.GetCheckpoint();
    TruckExitLocation = Saved->ExitLocation;
    TruckExitSeconds = Saved->TruckExitSeconds;
}

bool ANightShiftWorkOrder::RetryCheckpoint(APawn* Pawn)
{
    if (!IsPlayerPawn(Pawn))
    {
        return false;
    }
    const Phase Stage = LastCheckpoint.Current;
    if ((Stage == Phase::Striping || Stage == Phase::Detour || Stage == Phase::ReturnToYard) && !IsWorkTruck(*Pawn))
    {
        return false;
    }
    USceneComponent* Restart = YardCheckpoint.Get();
    if (Stage == Phase::Striping || Stage == Phase::Detour)
    {
        Restart = WorkCheckpoint.Get();
    }
    else if (Stage == Phase::ReturnToYard)
    {
        Restart = LastCheckpoint.Route == Exit::Detour ? DetourExit.Get() : RecoveryExit.Get();
    }
    if (!Pawn->TeleportTo(Restart->GetComponentLocation(), Restart->GetComponentRotation()))
    {
        return false;
    }
    if (UPawnMovementComponent* Movement = Pawn->GetMovementComponent())
    {
        Movement->StopMovementImmediately();
    }
    if (UPrimitiveComponent* Body = Cast<UPrimitiveComponent>(Pawn->GetRootComponent()))
    {
        if (Body->IsSimulatingPhysics())
        {
            Body->SetPhysicsLinearVelocity(FVector::ZeroVector);
            Body->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
        }
    }
    Order.Restore(LastCheckpoint);
    OwnerController = Cast<APlayerController>(Pawn->GetController());
    CancelStripe();
    bInsideWorkZone = Stage == Phase::Striping && ContainsPawn(*WorkZone, *Pawn);
    RefreshWorld();
    OnProgressChanged.Broadcast(GetPhase());
    return true;
}
