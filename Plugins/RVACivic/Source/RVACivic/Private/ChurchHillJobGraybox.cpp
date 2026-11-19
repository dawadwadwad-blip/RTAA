#include "ChurchHillJobGraybox.h"

#include "Components/BoxComponent.h"
#include "Components/InputComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Kismet/GameplayStatics.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
using namespace RVA::ChurchHill;
static_assert(static_cast<uint8>(HillRoute::Unset) == static_cast<uint8>(EChurchHillRoute::Unset));
static_assert(static_cast<uint8>(HillRoute::Gentle) == static_cast<uint8>(EChurchHillRoute::Gentle));
static_assert(static_cast<uint8>(HillRoute::Direct) == static_cast<uint8>(EChurchHillRoute::Direct));
static_assert(static_cast<uint8>(SurveyMethod::None) == static_cast<uint8>(ESurveyStakesMethod::None));
static_assert(static_cast<uint8>(SurveyMethod::Kind) == static_cast<uint8>(ESurveyStakesMethod::Kind));
static_assert(static_cast<uint8>(SurveyMethod::Hard) == static_cast<uint8>(ESurveyStakesMethod::Hard));
}

AChurchHillJobGraybox::AChurchHillJobGraybox()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickInterval = 0.1f;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("JobOrigin")));
}

UBoxComponent* AChurchHillJobGraybox::MakeZone(FName Name, const FVector& Center)
{
    UBoxComponent* Zone = CreateDefaultSubobject<UBoxComponent>(Name);
    Zone->SetupAttachment(GetRootComponent());
    Zone->SetRelativeLocation(Center);
    Zone->InitBoxExtent(FVector(245, 165, 210));
    Zone->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    return Zone;
}

UTextRenderComponent* AChurchHillJobGraybox::MakeSign(FName Name, USceneComponent& Parent,
    const FVector& RelativePosition)
{
    UTextRenderComponent* Sign = CreateDefaultSubobject<UTextRenderComponent>(Name);
    Sign->SetupAttachment(&Parent);
    Sign->SetRelativeLocation(RelativePosition);
    Sign->SetRelativeRotation(FRotator(0, 180, 0));
    Sign->SetHorizontalAlignment(EHTA_Center);
    Sign->SetWorldSize(24.0f);
    return Sign;
}

UStaticMeshComponent* AChurchHillJobGraybox::MakeProp(FName Name, USceneComponent& Parent,
    const FVector& Dimensions)
{
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    UStaticMeshComponent* Prop = CreateDefaultSubobject<UStaticMeshComponent>(Name);
    Prop->SetupAttachment(&Parent);
    Prop->SetStaticMesh(Cube.Object);
    Prop->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Prop->SetGenerateOverlapEvents(false);
    Prop->SetRelativeScale3D(Dimensions / 100.0);
    return Prop;
}

bool AChurchHillJobGraybox::Contains(const UBoxComponent& Zone, const APawn& Pawn)
{
    const FVector Local = Zone.GetComponentTransform().InverseTransformPosition(Pawn.GetActorLocation());
    const FVector Extent = Zone.GetUnscaledBoxExtent();
    return FMath::Abs(Local.X) <= Extent.X && FMath::Abs(Local.Y) <= Extent.Y && FMath::Abs(Local.Z) <= Extent.Z;
}

double AChurchHillJobGraybox::SpeedMps(const APawn& Pawn)
{
    return Pawn.GetVelocity().Size() / 100.0;
}

bool AChurchHillJobGraybox::IsLocalPawn(const APawn* Pawn) const
{
    if (!HasAuthority() || !IsValid(Pawn) || Pawn->GetWorld() != GetWorld())
    {
        return false;
    }
    const APlayerController* Controller = Cast<APlayerController>(Pawn->GetController());
    return Controller && Controller->IsLocalController() && Controller->GetPawn() == Pawn;
}

bool AChurchHillJobGraybox::PerformObjective(APawn* Pawn)
{
    return !bCompleted && IsLocalPawn(Pawn) && Advance(*Pawn);
}

void AChurchHillJobGraybox::BindTestKey(APlayerController* Controller)
{
    if (!bBindTestKey || TestController.IsValid() || !Controller || !Controller->IsLocalController())
    {
        return;
    }
    EnableInput(Controller);
    if (InputComponent)
    {
        TestController = Controller;
        if (!bBound)
        {
            InputComponent->BindKey(EKeys::E, IE_Pressed, this, &AChurchHillJobGraybox::HandleTestKey).bConsumeInput = false;
            bBound = true;
        }
    }
}

void AChurchHillJobGraybox::HandleTestKey()
{
    if (APlayerController* Controller = TestController.Get())
    {
        PerformObjective(Controller->GetPawn());
    }
}

void AChurchHillJobGraybox::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!HasAuthority() || bCompleted)
    {
        return;
    }
    APlayerController* Controller = UGameplayStatics::GetPlayerController(this, 0);
    BindTestKey(Controller);
    APawn* Pawn = Controller ? Controller->GetPawn() : nullptr;
    UpdateJob(IsLocalPawn(Pawn) ? Pawn : nullptr, DeltaSeconds);
}

void AChurchHillJobGraybox::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (APlayerController* Controller = TestController.Get())
    {
        DisableInput(Controller);
    }
    Super::EndPlay(EndPlayReason);
}

AHillClimbGraybox::AHillClimbGraybox()
{
    Pickup = MakeZone(TEXT("CornicePickup"), FVector(0, 0, 70));
    GentleGate = MakeZone(TEXT("GentleHill"), FVector(1450, 530, 70));
    DirectGate = MakeZone(TEXT("DirectHill"), FVector(950, -530, 70));
    Warning = MakeZone(TEXT("FinalGradeWarning"), FVector(2450, 0, 70));
    PullOff = MakeZone(TEXT("StrapPullOff"), FVector(3140, 0, 70));
    Delivery = MakeZone(TEXT("CorniceDelivery"), FVector(3990, 0, 70));
    Cornice = MakeProp(TEXT("Cornice"), *Pickup, FVector(190, 68, 26));
    Cornice->SetRelativeLocation(FVector(0, -115, -46));
    PickupSign = MakeSign(TEXT("PickupSign"), *Pickup, FVector(0, 0, 140));
    PullOffSign = MakeSign(TEXT("PullOffSign"), *PullOff, FVector(0, 0, 140));
    WarningSign = MakeSign(TEXT("WarningSign"), *Warning, FVector(0, 0, 140));
    DeliverySign = MakeSign(TEXT("DeliverySign"), *Delivery, FVector(0, 0, 140));
    MakeSign(TEXT("GentleSign"), *GentleGate, FVector(0, 0, 140))->SetText(
        NSLOCTEXT("ChurchHill", "GentleRoad", "LONGER ROUTE\nGentle grade [E]"));
    MakeSign(TEXT("DirectSign"), *DirectGate, FVector(0, 0, 140))->SetText(
        NSLOCTEXT("ChurchHill", "DirectRoad", "DIRECT ROUTE\nSteep grade [E]"));
}

void AHillClimbGraybox::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    RefreshSigns();
}

void AHillClimbGraybox::BeginPlay()
{
    Super::BeginPlay();
    RefreshSigns();
}

EChurchHillRoute AHillClimbGraybox::GetRoute() const
{
    return static_cast<EChurchHillRoute>(Progress.GetRoute());
}

FText AHillClimbGraybox::GetObjective() const
{
    switch (Progress.GetPhase())
    {
        case HillPhase::AwaitingLoad:
            return NSLOCTEXT("ChurchHill", "Load", "LOAD THE CORNICE\nStop the work truck here and press E");
        case HillPhase::ChooseRoute:
            return NSLOCTEXT("ChurchHill", "ChooseHill", "CHOOSE A HILL ROUTE\nUse the signed gate");
        case HillPhase::Hauling:
            return NSLOCTEXT("ChurchHill", "DeliverCornice", "HAUL THE CORNICE\nWatch the load on the grades");
        case HillPhase::StopToSecure:
            return NSLOCTEXT("ChurchHill", "SecureCornice", "STRAP LOOSE\nStop at the pull-off and press E");
        default:
            return NSLOCTEXT("ChurchHill", "DeliveredCornice", "CORNICE DELIVERED");
    }
}

void AHillClimbGraybox::ParkCornice(UBoxComponent& Site)
{
    Cornice->AttachToComponent(&Site, FAttachmentTransformRules::SnapToTargetNotIncludingScale);
    Cornice->SetRelativeLocationAndRotation(FVector(0, -115, -46), FRotator::ZeroRotator);
}

void AHillClimbGraybox::RefreshSigns()
{
    PickupSign->SetText(GetObjective());
    PullOffSign->SetText(Progress.GetPhase() == HillPhase::StopToSecure ? GetObjective() :
        NSLOCTEXT("ChurchHill", "PullOff", "SAFE PULL-OFF"));
    WarningSign->SetText(Progress.GetPhase() == HillPhase::StopToSecure ? GetObjective() :
        NSLOCTEXT("ChurchHill", "WatchGrade", "FINAL GRADE\nSlow for the pull-off"));
    DeliverySign->SetText(IsComplete() ? GetObjective() :
        NSLOCTEXT("ChurchHill", "Delivery", "CORNICE DROP-OFF\nStop and press E once secured"));
}

bool AHillClimbGraybox::Advance(APawn& Pawn)
{
    if (!Pawn.ActorHasTag(TruckTag))
    {
        return false;
    }
    const double Speed = SpeedMps(Pawn);
    if (Progress.GetPhase() == HillPhase::AwaitingLoad)
    {
        if (!Contains(*Pickup, Pawn) || Speed > 0.8 || !Pawn.GetRootComponent()
            || !Cornice->AttachToComponent(Pawn.GetRootComponent(), FAttachmentTransformRules::SnapToTargetNotIncludingScale))
        {
            return false;
        }
        Cornice->SetRelativeLocationAndRotation(CargoOffsetCm, FRotator::ZeroRotator);
        CargoTruck = &Pawn;
        Progress.Load();
    }
    else if (CargoTruck.Get() != &Pawn)
    {
        return false;
    }
    else if (Progress.GetPhase() == HillPhase::ChooseRoute)
    {
        const HillRoute Choice = Contains(*GentleGate, Pawn) ? HillRoute::Gentle
            : (Contains(*DirectGate, Pawn) ? HillRoute::Direct : HillRoute::Unset);
        if (!Progress.Choose(Choice))
        {
            return false;
        }
    }
    else if (Progress.GetPhase() == HillPhase::StopToSecure)
    {
        if (!Contains(*PullOff, Pawn) || !Progress.Secure(Speed))
        {
            return false;
        }
        Cornice->SetRelativeLocation(CargoOffsetCm);
    }
    else
    {
        if (!Contains(*Delivery, Pawn) || !Progress.Deliver(Speed))
        {
            return false;
        }
        ParkCornice(*Delivery);
        CargoTruck.Reset();
        MarkComplete();
        OnDelivered.Broadcast(GetRoute());
    }
    RefreshSigns();
    return true;
}

void AHillClimbGraybox::UpdateJob(APawn* Pawn, float DeltaSeconds)
{
    if (!CargoTruck.IsValid() && Progress.ResetIfCargoLost())
    {
        ParkCornice(*Pickup);
        RefreshSigns();
        return;
    }
    if (!Pawn || CargoTruck.Get() != Pawn || Progress.GetPhase() != HillPhase::Hauling)
    {
        return;
    }
    const double PitchRatio = Pawn->GetActorForwardVector().Z;
    const bool bWarned = (Contains(*Warning, *Pawn) && Progress.ReachWarning())
        || Progress.RecordDrive(PitchRatio, SpeedMps(*Pawn), DeltaSeconds);
    Cornice->SetRelativeLocation(CargoOffsetCm + FVector(-Progress.GetSlip() * 48.0, 0, 0));
    if (bWarned)
    {
        RefreshSigns();
    }
}

ASurveyStakesGraybox::ASurveyStakesGraybox()
{
    KindBrief = MakeZone(TEXT("ReviewBoardBrief"), FVector(0, 380, 70));
    HardBrief = MakeZone(TEXT("MortarCircleBrief"), FVector(0, -380, 70));
    SiteA = MakeZone(TEXT("OccupiedStoopA"), FVector(1050, 0, 70));
    SiteB = MakeZone(TEXT("OccupiedStoopB"), FVector(1980, 0, 70));
    StakeA = MakeProp(TEXT("SurveyStakeA"), *SiteA, FVector(12, 12, 105));
    StakeB = MakeProp(TEXT("SurveyStakeB"), *SiteB, FVector(12, 12, 105));
    KindSign = MakeSign(TEXT("KindBriefSign"), *KindBrief, FVector(0, 0, 140));
    HardSign = MakeSign(TEXT("HardBriefSign"), *HardBrief, FVector(0, 0, 140));
    BoardA = MakeSign(TEXT("OccupiedBoardA"), *SiteA, FVector(0, 100, 120));
    BoardB = MakeSign(TEXT("OccupiedBoardB"), *SiteB, FVector(0, 100, 120));
    LoadingGate = MakeZone(TEXT("HardLoadingBarrier"), FVector(2200, -390, 52));
    LoadingGate->SetBoxExtent(FVector(28, 160, 52));
    LoadingGate->SetCollisionObjectType(ECC_WorldStatic);
    LoadingGate->SetCollisionResponseToAllChannels(ECR_Block);
    LoadingBarrier = MakeProp(TEXT("LoadingBarrier"), *LoadingGate, FVector(56, 320, 104));
    LoadingSign = MakeSign(TEXT("LoadingApproachSign"), *LoadingGate, FVector(0, 0, 113));
}

void ASurveyStakesGraybox::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    RefreshWorld();
}

void ASurveyStakesGraybox::BeginPlay()
{
    Super::BeginPlay();
    RefreshWorld();
}

ESurveyStakesMethod ASurveyStakesGraybox::GetMethod() const
{
    return static_cast<ESurveyStakesMethod>(Progress.GetMethod());
}

bool ASurveyStakesGraybox::IsDeliveryDiverted() const
{
    return IsComplete() && Progress.GetMethod() == SurveyMethod::Hard;
}

bool ASurveyStakesGraybox::Advance(APawn& Pawn)
{
    if (SpeedMps(Pawn) > 1.0)
    {
        return false;
    }
    if (Progress.GetPhase() == SurveyPhase::Available)
    {
        const SurveyMethod Choice = Contains(*KindBrief, Pawn) ? SurveyMethod::Kind
            : (Contains(*HardBrief, Pawn) ? SurveyMethod::Hard : SurveyMethod::None);
        if (!Progress.Begin(Choice, FMath::Clamp(HardTimeLimitSeconds, 5.0f, 300.0f)))
        {
            return false;
        }
        bTimedOut = false;
    }
    else
    {
        const uint8 Site = Contains(*SiteA, Pawn) ? 0 : (Contains(*SiteB, Pawn) ? 1 : 2);
        if (!Progress.MarkSite(Site))
        {
            return false;
        }
        if (Progress.GetPhase() == SurveyPhase::Complete)
        {
            MarkComplete();
            OnResolved.Broadcast(GetMethod());
        }
    }
    RefreshWorld();
    return true;
}

void ASurveyStakesGraybox::UpdateJob(APawn*, float DeltaSeconds)
{
    const bool bExpired = Progress.Tick(DeltaSeconds);
    const int32 Seconds = FMath::CeilToInt(Progress.GetSecondsLeft());
    if (bExpired || Seconds != LastSecondsShown)
    {
        bTimedOut = bExpired;
        RefreshWorld();
    }
}

void ASurveyStakesGraybox::RefreshWorld()
{
    const bool bWorking = Progress.GetPhase() == SurveyPhase::Working;
    const bool bHard = Progress.GetMethod() == SurveyMethod::Hard;
    LastSecondsShown = FMath::CeilToInt(Progress.GetSecondsLeft());
    KindSign->SetText(bWorking
        ? NSLOCTEXT("ChurchHill", "BothStoops", "FINISH BOTH MARKED STOOPS")
        : NSLOCTEXT("ChurchHill", "KindBrief", "REVIEW BOARD [E]\nMark occupied homes, keep access open"));
    HardSign->SetText(bWorking && bHard
        ? FText::Format(NSLOCTEXT("ChurchHill", "SurveyCountdown", "MORTAR CIRCLE\n{0} seconds left"),
            FText::AsNumber(LastSecondsShown))
        : NSLOCTEXT("ChurchHill", "HardBrief", "MORTAR CIRCLE [E]\nTimed marker swap, deliveries diverted"));
    const bool bDiverted = IsDeliveryDiverted();
    LoadingGate->SetCollisionEnabled(bDiverted ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
    LoadingBarrier->SetVisibility(bDiverted);
    LoadingSign->SetText(bDiverted
        ? NSLOCTEXT("ChurchHill", "LoadingDiverted", "LOCAL DELIVERY DIVERTED")
        : NSLOCTEXT("ChurchHill", "LoadingOpen", "LOADING ACCESS OPEN"));

    const auto UpdateSite = [this, bWorking, bHard](uint8 Index, UStaticMeshComponent& Stake, UTextRenderComponent& Board)
    {
        const bool bDone = Progress.HasSite(Index);
        Stake.SetRelativeLocation(FVector(0, bDone && bHard ? 125 : 0, -18));
        FText Label = NSLOCTEXT("ChurchHill", "StoopIdle", "SURVEY STAKE");
        if (bDone)
        {
            Label = bHard ? NSLOCTEXT("ChurchHill", "SwapDone", "STAKE MOVED")
                          : NSLOCTEXT("ChurchHill", "Occupied", "OCCUPIED HOME");
        }
        else if (bWorking && bHard)
        {
            Label = FText::Format(NSLOCTEXT("ChurchHill", "SwapHere", "SWAP STAKE [E]\n{0} seconds left"),
                FText::AsNumber(LastSecondsShown));
        }
        else if (bWorking)
        {
            Label = NSLOCTEXT("ChurchHill", "MarkHere", "MARK OCCUPIED HOME [E]");
        }
        else if (bTimedOut)
        {
            Label = NSLOCTEXT("ChurchHill", "SurveyReset", "TIME EXPIRED\nReturn to the briefing");
        }
        Board.SetText(Label);
    };
    UpdateSite(0, *StakeA, *BoardA);
    UpdateSite(1, *StakeB, *BoardB);
}
