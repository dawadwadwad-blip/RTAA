#include "ChurchHillSliceDirector.h"

#include "Components/SceneComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "NightShiftWorkOrder.h"
#include "Templates/UnrealTemplate.h"

DEFINE_LOG_CATEGORY_STATIC(LogChurchHillSlice, Log, All);

namespace
{
using RVA::Slice::Job;

FName MissionId(Job Item)
{
    switch (Item)
    {
        case Job::NightShift: return FName(TEXT("M01"));
        case Job::HillClimb: return FName(TEXT("M13"));
        case Job::SurveyStakes: return FName(TEXT("M04"));
        default: return NAME_None;
    }
}

FText JobName(Job Item)
{
    switch (Item)
    {
        case Job::NightShift: return NSLOCTEXT("ChurchHillSlice", "Night", "M01  NIGHT SHIFT");
        case Job::HillClimb: return NSLOCTEXT("ChurchHillSlice", "Hill", "M13  HILL CLIMB");
        case Job::SurveyStakes: return NSLOCTEXT("ChurchHillSlice", "Survey", "M04  SURVEY STAKES");
        default: return NSLOCTEXT("ChurchHillSlice", "Done", "CHURCH HILL SLICE COMPLETE");
    }
}

FCivicWorkOrderDefinition MakeOrder(Job Item)
{
    FCivicWorkOrderDefinition Definition;
    Definition.MissionId = MissionId(Item);
    Definition.District = FName(TEXT("ChurchHill"));
    Definition.ZoneId = Definition.MissionId;
    Definition.OfferedMethods.Add(ECivicWorkMethod::Kind);
    if (Item != Job::NightShift)
    {
        Definition.OfferedMethods.Add(ECivicWorkMethod::Hard);
    }
    switch (Item)
    {
        case Job::HillClimb: Definition.Verb = ECivicWorkVerb::Deliver; break;
        case Job::SurveyStakes: Definition.Verb = ECivicWorkVerb::Swap; break;
        default: Definition.Verb = ECivicWorkVerb::Stripe; break;
    }
    return Definition;
}
}

AChurchHillSliceDirector::AChurchHillSliceDirector()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickInterval = 0.2f;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("SliceRoot")));
    ProgressSign = CreateDefaultSubobject<UTextRenderComponent>(TEXT("SliceProgress"));
    ProgressSign->SetupAttachment(GetRootComponent());
    ProgressSign->SetRelativeLocation(FVector(0, 0, 230));
    ProgressSign->SetRelativeRotation(FRotator(0, 180, 0));
    ProgressSign->SetHorizontalAlignment(EHTA_Center);
    ProgressSign->SetWorldSize(30.0f);
    ProgressSign->SetText(JobName(Job::NightShift));
}

void AChurchHillSliceDirector::BeginPlay()
{
    Super::BeginPlay();
    if (!HasAuthority())
    {
        return;
    }
    if (!IsValid(NightShift.Get()) || !IsValid(HillClimb.Get()) || !IsValid(SurveyStakes.Get())
        || NightShift->GetWorld() != GetWorld() || HillClimb->GetWorld() != GetWorld()
        || SurveyStakes->GetWorld() != GetWorld())
    {
        ProgressSign->SetText(NSLOCTEXT("ChurchHillSlice", "MissingActors", "Assign all three slice jobs"));
        return;
    }
    if (NightShift->bPersistCheckpoint)
    {
        ProgressSign->SetText(NSLOCTEXT("ChurchHillSlice", "StandaloneSave",
            "Turn off the standalone Night Shift save for this session slice"));
        return;
    }
    Ledger = GetWorld()->GetSubsystem<UCivicWorkOrderSubsystem>();
    if (!Ledger)
    {
        ProgressSign->SetText(NSLOCTEXT("ChurchHillSlice", "NoLedger", "Campaign ledger unavailable"));
        return;
    }

    NightShift->OnDebriefCompleted.AddUniqueDynamic(this, &AChurchHillSliceDirector::HandleNight);
    HillClimb->OnDelivered.AddUniqueDynamic(this, &AChurchHillSliceDirector::HandleHill);
    SurveyStakes->OnResolved.AddUniqueDynamic(this, &AChurchHillSliceDirector::HandleSurvey);
    RefreshSlice();
}

void AChurchHillSliceDirector::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (Ledger && bOwnsActiveOrder && Ledger->HasActiveWorkOrder()
        && Ledger->GetActiveWorkOrder().MissionId == GetCurrentMissionId())
    {
        Ledger->AbandonWorkOrder();
    }
    Super::EndPlay(EndPlayReason);
}

void AChurchHillSliceDirector::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!Ledger || !PlaytestTruckClass || !IsValid(NightShift.Get()) || !IsValid(HillClimb.Get()))
    {
        return;
    }
    APawn* Pawn = UGameplayStatics::GetPlayerPawn(this, 0);
    if (IsValid(Pawn) && Pawn != TaggedPawn.Get() && Pawn->IsA(PlaytestTruckClass.Get()))
    {
        TaggedPawn = Pawn;
        Pawn->Tags.AddUnique(NightShift->TruckTag);
        Pawn->Tags.AddUnique(HillClimb->TruckTag);
    }
}

FName AChurchHillSliceDirector::GetCurrentMissionId() const
{
    return MissionId(Jobs.Current());
}

void AChurchHillSliceDirector::EnableOnly(Job Item)
{
    NightShift->SetSliceEnabled(Item == Job::NightShift);
    HillClimb->SetSliceEnabled(Item == Job::HillClimb);
    SurveyStakes->SetSliceEnabled(Item == Job::SurveyStakes);
}

bool AChurchHillSliceDirector::EnsureOrder()
{
    if (bOwnsActiveOrder && Ledger->HasActiveWorkOrder()
        && Ledger->GetActiveWorkOrder().MissionId == GetCurrentMissionId())
    {
        return true;
    }
    if (Ledger->HasActiveWorkOrder())
    {
        return false;
    }
    bMethodSelected = false;
    bOwnsActiveOrder = Ledger->BeginWorkOrder(MakeOrder(Jobs.Current()));
    return bOwnsActiveOrder;
}

const FCivicWorkOrderOutcome& AChurchHillSliceDirector::OutcomeFor(Job Item) const
{
    if (Item == Job::HillClimb)
    {
        return bHillDirect ? HillDirectOutcome : HillGentleOutcome;
    }
    if (Item == Job::SurveyStakes)
    {
        return PendingMethod.GetValue() == ECivicWorkMethod::Hard ? SurveyHardOutcome : SurveyKindOutcome;
    }
    return NightOutcome;
}

bool AChurchHillSliceDirector::RefreshSlice()
{
    if (!HasAuthority() || !Ledger || bRefreshing || !IsValid(NightShift.Get())
        || !IsValid(HillClimb.Get()) || !IsValid(SurveyStakes.Get()))
    {
        return false;
    }
    TGuardValue<bool> Guard(bRefreshing, true);
    while (Jobs.Current() != Job::Complete && Ledger->WasWorkOrderCompleted(GetCurrentMissionId()))
    {
        Jobs.Resolve(Jobs.Current());
        PendingMethod.Reset();
        bOwnsActiveOrder = false;
    }
    if (Jobs.Current() == Job::Complete)
    {
        EnableOnly(Job::Complete);
        ProgressSign->SetText(JobName(Job::Complete));
        return true;
    }
    if (!EnsureOrder())
    {
        EnableOnly(Job::Complete);
        ProgressSign->SetText(NSLOCTEXT("ChurchHillSlice", "Blocked", "Finish the active campaign order first"));
        return false;
    }
    if (PendingMethod.IsSet())
    {
        EnableOnly(Job::Complete);
        if (!bMethodSelected)
        {
            bMethodSelected = Ledger->SelectWorkMethod(PendingMethod.GetValue());
        }
        const Job Item = Jobs.Current();
        if (!bMethodSelected || !Ledger->CompleteWorkOrder(OutcomeFor(Item)))
        {
            ProgressSign->SetText(NSLOCTEXT("ChurchHillSlice", "NotFiled", "Outcome pending review"));
            return false;
        }
        const FCivicCampaignProgress Progress = Ledger->GetCampaignProgress();
        UE_LOG(LogChurchHillSlice, Display,
            TEXT("Filed %s (%s). Completed: %d, helped: %lld, harmed: %lld, collateral: %lld, Church Hill strain: %d"),
            *MissionId(Item).ToString(), *UEnum::GetValueAsString(PendingMethod.GetValue()),
            Progress.CompletedWorkOrders, Progress.HouseholdsHelped, Progress.HouseholdsHarmed,
            Progress.Collateral, Ledger->GetDistrictStrain(FName(TEXT("ChurchHill"))));
        Jobs.Resolve(Item);
        PendingMethod.Reset();
        bOwnsActiveOrder = false;
        if (Jobs.Current() != Job::Complete && !EnsureOrder())
        {
            ProgressSign->SetText(NSLOCTEXT("ChurchHillSlice", "BlockedAfter", "Finish the active campaign order first"));
            return false;
        }
    }
    EnableOnly(Jobs.Current());
    ProgressSign->SetText(JobName(Jobs.Current()));
    return true;
}

void AChurchHillSliceDirector::HandleNight()
{
    if (Jobs.Current() == Job::NightShift && !PendingMethod.IsSet())
    {
        PendingMethod = ECivicWorkMethod::Kind;
        RefreshSlice();
    }
}

void AChurchHillSliceDirector::HandleHill(EChurchHillRoute Route)
{
    if (Jobs.Current() == Job::HillClimb && !PendingMethod.IsSet() && Route != EChurchHillRoute::Unset)
    {
        bHillDirect = Route == EChurchHillRoute::Direct;
        PendingMethod = bHillDirect ? ECivicWorkMethod::Hard : ECivicWorkMethod::Kind;
        RefreshSlice();
    }
}

void AChurchHillSliceDirector::HandleSurvey(ESurveyStakesMethod Method)
{
    if (Jobs.Current() == Job::SurveyStakes && !PendingMethod.IsSet() && Method != ESurveyStakesMethod::None)
    {
        PendingMethod = Method == ESurveyStakesMethod::Hard ? ECivicWorkMethod::Hard : ECivicWorkMethod::Kind;
        RefreshSlice();
    }
}
