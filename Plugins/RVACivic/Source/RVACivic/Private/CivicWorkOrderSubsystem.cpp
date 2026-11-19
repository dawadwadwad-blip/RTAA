#include "CivicWorkOrderSubsystem.h"

#include "CivicCampaignRules.h"
#include "Engine/World.h"

bool UCivicWorkOrderSubsystem::DoesSupportWorldType(EWorldType::Type WorldType) const
{
    return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

bool UCivicWorkOrderSubsystem::CanMutate() const
{
    const UWorld* World = GetWorld();
    return World && World->GetNetMode() != NM_Client;
}

bool UCivicWorkOrderSubsystem::BeginWorkOrder(const FCivicWorkOrderDefinition& Definition)
{
    if (!CanMutate() || bWorkOrderActive || Definition.MissionId.IsNone()
        || Definition.District.IsNone() || ResolvedOrderIds.Contains(Definition.MissionId)
        || Definition.OfferedMethods.IsEmpty()
        || !StaticEnum<ECivicWorkVerb>()->IsValidEnumValue(static_cast<int64>(Definition.Verb)))
    {
        return false;
    }
    for (ECivicWorkMethod Method : Definition.OfferedMethods)
    {
        if (!StaticEnum<ECivicWorkMethod>()->IsValidEnumValue(static_cast<int64>(Method)))
        {
            return false;
        }
    }

    ActiveOrder = Definition;
    bWorkOrderActive = true;
    bMethodChosen = false;
    ActiveMethod = ECivicWorkMethod::Kind;
    return true;
}

bool UCivicWorkOrderSubsystem::SelectWorkMethod(ECivicWorkMethod Method)
{
    if (!CanMutate() || !bWorkOrderActive || bMethodChosen
        || !ActiveOrder.OfferedMethods.Contains(Method)
        || !StaticEnum<ECivicWorkMethod>()->IsValidEnumValue(static_cast<int64>(Method)))
    {
        return false;
    }
    ActiveMethod = Method;
    bMethodChosen = true;
    return true;
}

bool UCivicWorkOrderSubsystem::CompleteWorkOrder(const FCivicWorkOrderOutcome& Outcome)
{
    if (!CanMutate() || !bWorkOrderActive || !bMethodChosen
        || ResolvedOrderIds.Contains(ActiveOrder.MissionId)
        || Progress.CompletedWorkOrders == MAX_int32)
    {
        return false;
    }

    RVA::Campaign::Totals NewTotals{
        Progress.HouseholdsHelped,
        Progress.HouseholdsHarmed,
        Progress.Collateral
    };
    const RVA::Campaign::Outcome Delta{
        Outcome.HouseholdsHelped,
        Outcome.HouseholdsHarmed,
        Outcome.Collateral
    };
    if (!RVA::Campaign::ApplyOnce(NewTotals, Delta))
    {
        return false;
    }

    // Apply every result atomically after the validity/overflow checks.
    Progress.HouseholdsHelped = NewTotals.Helped;
    Progress.HouseholdsHarmed = NewTotals.Harmed;
    Progress.Collateral = NewTotals.Collateral;
    Progress.ComplianceTier = RVA::Campaign::ClampComplianceTier(
        Progress.ComplianceTier, Outcome.ComplianceTierDelta);
    const FName District = ActiveOrder.District;
    DistrictStrain.Add(District, RVA::Campaign::ClampStrain(
        DistrictStrain.FindRef(District), Outcome.DistrictStrainDelta));
    ++Progress.CompletedWorkOrders;

    const FName CompletedId = ActiveOrder.MissionId;
    ResolvedOrderIds.Add(CompletedId);
    ActiveOrder = FCivicWorkOrderDefinition{};
    bWorkOrderActive = false;
    bMethodChosen = false;

    OnWorkOrderCompleted.Broadcast(CompletedId, Progress);
    return true;
}

bool UCivicWorkOrderSubsystem::AbandonWorkOrder()
{
    if (!CanMutate() || !bWorkOrderActive)
    {
        return false;
    }
    ActiveOrder = FCivicWorkOrderDefinition{};
    bWorkOrderActive = false;
    bMethodChosen = false;
    return true;
}

bool UCivicWorkOrderSubsystem::IsAuthorizedWorkZone(
    FName ZoneId, bool bWearingVest, bool bConesDeployed) const
{
    return bWorkOrderActive && bMethodChosen && bWearingVest && bConesDeployed
        && !ZoneId.IsNone() && ZoneId == ActiveOrder.ZoneId;
    // A physical radius reduced by district Strain is authored separately.
}

int32 UCivicWorkOrderSubsystem::GetDistrictStrain(FName District) const
{
    return DistrictStrain.FindRef(District);
}

bool UCivicWorkOrderSubsystem::WasWorkOrderCompleted(FName MissionId) const
{
    return !MissionId.IsNone() && ResolvedOrderIds.Contains(MissionId);
}

bool UCivicWorkOrderSubsystem::UnlockWingContact(FName ContactId, bool bMeansWing)
{
    if (!CanMutate() || ContactId.IsNone())
    {
        return false;
    }
    if (bMeansWing)
    {
        MeansContacts.Add(ContactId);
    }
    else
    {
        BelieverContacts.Add(ContactId);
    }
    return true;
}

bool UCivicWorkOrderSubsystem::UnlockCommitteeProcedure()
{
    if (!CanMutate())
    {
        return false;
    }
    bCommitteeProcedureUnlocked = true;
    return true;
}

bool UCivicWorkOrderSubsystem::IsEndingEligible(ECivicCampaignEnding Ending) const
{
    switch (Ending)
    {
        case ECivicCampaignEnding::Built:
            return true;
        case ECivicCampaignEnding::Frozen:
            return bCommitteeProcedureUnlocked;
        case ECivicCampaignEnding::ThirdAlignment:
            return RVA::Campaign::ThirdAlignmentEligible(
                Progress.Collateral, ThirdAlignmentMaxCollateral, !BelieverContacts.IsEmpty());
        case ECivicCampaignEnding::TheFixer:
            return RVA::Campaign::FixerEligible(
                Progress.Collateral, FixerMinCollateral, !MeansContacts.IsEmpty());
        default:
            return false;
    }
}
