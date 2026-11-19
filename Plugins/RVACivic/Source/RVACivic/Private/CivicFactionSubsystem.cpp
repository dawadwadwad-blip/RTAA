#include "CivicFactionSubsystem.h"

#include "CivicPolicyMath.h"

#include "Engine/World.h"
#include "WorldPartition/DataLayer/DataLayerAsset.h"
#include "WorldPartition/DataLayer/DataLayerInstance.h"
#include "WorldPartition/DataLayer/DataLayerManager.h"

namespace
{
namespace Policy = RVA::CivicPolicy;

const TPair<ECivicFaction, ECivicFaction> Rivalries[] = {
    {ECivicFaction::AlbanicoAssociation, ECivicFaction::ThePod},
    {ECivicFaction::CargoBikeMilitia, ECivicFaction::AsphaltCoalition},
    {ECivicFaction::LocalIndependents, ECivicFaction::CorporateCapital},
    {ECivicFaction::UrbanCore, ECivicFaction::CountyAnnexation}
};

bool IsFaction(ECivicFaction Faction)
{
    return StaticEnum<ECivicFaction>()->IsValidEnumValue(static_cast<int64>(Faction));
}

EDataLayerRuntimeState ToRuntimeState(ECivicLayerState State)
{
    switch (State)
    {
        case ECivicLayerState::Activated: return EDataLayerRuntimeState::Activated;
        case ECivicLayerState::Loaded: return EDataLayerRuntimeState::Loaded;
        default: return EDataLayerRuntimeState::Unloaded;
    }
}

bool ApplyOverride(UDataLayerManager& Manager, const UDataLayerAsset& Layer, ECivicLayerState State)
{
    const UDataLayerInstance* Instance = Manager.GetDataLayerInstanceFromAsset(&Layer);
    if (!Instance || !Instance->IsRuntime())
    {
        return false;
    }
    const EDataLayerRuntimeState Desired = ToRuntimeState(State);
    if (Manager.GetDataLayerInstanceRuntimeState(Instance) != Desired)
    {
        Manager.SetDataLayerInstanceRuntimeState(Instance, Desired, false);
    }
    return Manager.GetDataLayerInstanceRuntimeState(Instance) == Desired;
}
}

bool UCivicFactionSubsystem::DoesSupportWorldType(EWorldType::Type WorldType) const
{
    return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UCivicFactionSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
    Super::OnWorldBeginPlay(InWorld);
    RefreshLayerOverrides();
}

bool UCivicFactionSubsystem::CanMutate() const
{
    const UWorld* World = GetWorld();
    return World && World->GetNetMode() != NM_Client;
}

int32 UCivicFactionSubsystem::GetReputation(ECivicFaction Faction) const
{
    return Reputation.FindRef(Faction);
}

bool UCivicFactionSubsystem::ChangeReputation(ECivicFaction Faction, int32 Delta)
{
    if (!CanMutate() || !IsFaction(Faction))
    {
        return false;
    }

    TArray<TPair<ECivicFaction, int32>, TInlineAllocator<2>> Changes;
    const auto ApplyDelta = [this, &Changes](ECivicFaction Target, int32 Amount)
    {
        const int32 OldValue = GetReputation(Target);
        const int32 NewValue = Policy::BoundedReputation(OldValue, Amount);
        if (OldValue != NewValue)
        {
            Reputation.Add(Target, NewValue);
            Changes.Emplace(Target, NewValue);
        }
    };

    const int32 Previous = GetReputation(Faction);
    ApplyDelta(Faction, Delta);
    if (!Changes.IsEmpty())
    {
        // The rival reacts to the actual movement after the reputation cap.
        const int32 RivalDelta = Policy::RivalResponse(GetReputation(Faction) - Previous);
        for (const auto& Rivalry : Rivalries)
        {
            if (Faction == Rivalry.Key || Faction == Rivalry.Value)
            {
                ApplyDelta(Faction == Rivalry.Key ? Rivalry.Value : Rivalry.Key, RivalDelta);
                break;
            }
        }
        CommitCityState();
        for (const auto& Change : Changes)
        {
            OnReputationChanged.Broadcast(Change.Key, Change.Value);
        }
    }
    return true;
}

bool UCivicFactionSubsystem::SetFiscalPolicy(int32 TaxRateBasisPoints, int32 AdministrativeShareBasisPoints)
{
    if (!CanMutate())
    {
        return false;
    }
    const int32 Tax = FMath::Clamp(TaxRateBasisPoints, 0, Policy::MaximumTax);
    const int32 Administration = FMath::Clamp(AdministrativeShareBasisPoints, 0, Policy::BasisPoints);
    if (Tax != CityState.TaxRateBasisPoints || Administration != CityState.AdministrativeShareBasisPoints)
    {
        CityState.TaxRateBasisPoints = Tax;
        CityState.AdministrativeShareBasisPoints = Administration;
        CommitCityState();
    }
    return true;
}

FCivicFiscalPeriod UCivicFactionSubsystem::EstimateFiscalPeriod(int64 TaxBaseCents) const
{
    FCivicFiscalPeriod Period;
    Period.TaxReceivedCents = Policy::Allocate(TaxBaseCents, CityState.TaxRateBasisPoints);
    Period.AdministrationCents = Policy::Allocate(Period.TaxReceivedCents, CityState.AdministrativeShareBasisPoints);
    Period.PublicWorksCents = Period.TaxReceivedCents - Period.AdministrationCents;
    return Period;
}

bool UCivicFactionSubsystem::AddRedTapeHeat(int32 Delta)
{
    if (!CanMutate())
    {
        return false;
    }
    const int32 Heat = FMath::Clamp(CityState.RedTapeHeat + FMath::Clamp(Delta, -100, 100), 0, 100);
    if (Heat != CityState.RedTapeHeat)
    {
        CityState.RedTapeHeat = Heat;
        CommitCityState();
    }
    return true;
}

void UCivicFactionSubsystem::CommitCityState()
{
    const Policy::Outcomes Outcome = Policy::Evaluate(CityState.TaxRateBasisPoints,
        CityState.AdministrativeShareBasisPoints, CityState.RedTapeHeat,
        GetReputation(ECivicFaction::MunicipalCommission));
    CityState.ResidentMorale = Outcome.ResidentMorale;
    CityState.LocalBusinessVitality = Outcome.BusinessVitality;
    CityState.bPermitsAvailable = Outcome.PermitsAvailable;
    RefreshLayerOverrides();
    OnCityStateChanged.Broadcast(CityState);
}

bool UCivicFactionSubsystem::RuleMatches(const FCivicLayerRule& Rule) const
{
    switch (Rule.Trigger)
    {
        case ECivicLayerTrigger::FactionFavored:
            return GetReputation(Rule.Faction) >= FMath::Clamp(Rule.ReputationThreshold, 1, 100);
        case ECivicLayerTrigger::PermitsAvailable:
            return CityState.bPermitsAvailable;
        case ECivicLayerTrigger::EnforcementActive:
            return CityState.RedTapeHeat >= Policy::EnforcementThreshold;
        default:
            return false;
    }
}

bool UCivicFactionSubsystem::ConfigureLayerOverrides(const TArray<FCivicLayerRule>& Rules)
{
    if (!CanMutate())
    {
        return false;
    }
    TSet<const UDataLayerAsset*> Assigned;
    for (const FCivicLayerRule& Rule : Rules)
    {
        if (!IsValid(Rule.Layer.Get()) || Assigned.Contains(Rule.Layer.Get()) || !IsFaction(Rule.Faction)
            || !StaticEnum<ECivicLayerTrigger>()->IsValidEnumValue(static_cast<int64>(Rule.Trigger))
            || !StaticEnum<ECivicLayerState>()->IsValidEnumValue(static_cast<int64>(Rule.ActiveState))
            || !StaticEnum<ECivicLayerState>()->IsValidEnumValue(static_cast<int64>(Rule.InactiveState)))
        {
            return false;
        }
        Assigned.Add(Rule.Layer.Get());
    }
    if (UDataLayerManager* Manager = UDataLayerManager::GetDataLayerManager(GetWorld()))
    {
        for (const FCivicLayerRule& Previous : LayerOverrides)
        {
            if (IsValid(Previous.Layer.Get()) && !Assigned.Contains(Previous.Layer.Get()))
            {
                ApplyOverride(*Manager, *Previous.Layer.Get(), Previous.InactiveState);
            }
        }
    }
    LayerOverrides = Rules;
    return RefreshLayerOverrides();
}

bool UCivicFactionSubsystem::RefreshLayerOverrides()
{
    if (!CanMutate())
    {
        return false;
    }
    if (LayerOverrides.IsEmpty())
    {
        return true;
    }
    UDataLayerManager* Manager = UDataLayerManager::GetDataLayerManager(GetWorld());
    if (!Manager)
    {
        return false;
    }
    bool bAllApplied = true;
    for (const FCivicLayerRule& Rule : LayerOverrides)
    {
        if (!IsValid(Rule.Layer.Get())
            || !ApplyOverride(*Manager, *Rule.Layer.Get(), RuleMatches(Rule) ? Rule.ActiveState : Rule.InactiveState))
        {
            bAllApplied = false;
        }
    }
    return bAllApplied;
}
