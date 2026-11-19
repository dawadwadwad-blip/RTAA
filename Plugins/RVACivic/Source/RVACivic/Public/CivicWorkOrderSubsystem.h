#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "CivicWorkOrderSubsystem.generated.h"

// v2 names deliberately differ from the older civic-fiscal and Chaos tool APIs.
UENUM(BlueprintType)
enum class ECivicWorkVerb : uint8
{
    Stripe, Patch, Tow, Deliver, Swap, Block, Tail
};

UENUM(BlueprintType)
enum class ECivicWorkMethod : uint8
{
    Kind, Pointed, Hard
};

UENUM(BlueprintType)
enum class ECivicCampaignEnding : uint8
{
    Built, Frozen, ThirdAlignment, TheFixer
};

USTRUCT(BlueprintType)
struct RVACIVIC_API FCivicWorkOrderDefinition
{
    GENERATED_BODY()

    // Stable identifier, e.g. M01. Not a human-readable localized title.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|WorkOrder")
    FName MissionId = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|WorkOrder")
    FName District = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|WorkOrder")
    FName ZoneId = NAME_None;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|WorkOrder")
    ECivicWorkVerb Verb = ECivicWorkVerb::Stripe;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|WorkOrder")
    TArray<ECivicWorkMethod> OfferedMethods;
};

USTRUCT(BlueprintType)
struct RVACIVIC_API FCivicWorkOrderOutcome
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|WorkOrder", meta = (ClampMin = "0"))
    int32 HouseholdsHelped = 0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|WorkOrder", meta = (ClampMin = "0"))
    int32 HouseholdsHarmed = 0;

    // Distinct from households harmed; e.g. damaged local property.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|WorkOrder", meta = (ClampMin = "0"))
    int32 Collateral = 0;

    // Tuned per mission and method. There are no hidden Hard-method penalties.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|WorkOrder")
    int32 ComplianceTierDelta = 0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|WorkOrder")
    int32 DistrictStrainDelta = 0;
};

USTRUCT(BlueprintType)
struct RVACIVIC_API FCivicCampaignProgress
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Civic|Campaign")
    int64 HouseholdsHelped = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Civic|Campaign")
    int64 HouseholdsHarmed = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Civic|Campaign")
    int64 Collateral = 0;

    // 0 none; 1 citation; 2 tow; 3 code enforcement; 4 police.
    // County handoff is a separate geographic rule to author later.
    UPROPERTY(BlueprintReadOnly, Category = "Civic|Campaign")
    int32 ComplianceTier = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Civic|Campaign")
    int32 CompletedWorkOrders = 0;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FCivicWorkOrderCompleted,
    FName, MissionId, const FCivicCampaignProgress&, Progress);

UCLASS(BlueprintType)
class RVACIVIC_API UCivicWorkOrderSubsystem final : public UWorldSubsystem
{
    GENERATED_BODY()

public:
    UPROPERTY(BlueprintAssignable, Category = "Civic|Campaign")
    FCivicWorkOrderCompleted OnWorkOrderCompleted;

    // -1 means unset. Restricted endings remain locked until the creator approves\n    // concrete Collateral thresholds; these are not invented defaults.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|Campaign|Tuning", meta = (ClampMin = "-1"))
    int64 ThirdAlignmentMaxCollateral = -1;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|Campaign|Tuning", meta = (ClampMin = "-1"))
    int64 FixerMinCollateral = -1;

    UFUNCTION(BlueprintCallable, Category = "Civic|WorkOrder")
    bool BeginWorkOrder(const FCivicWorkOrderDefinition& Definition);

    UFUNCTION(BlueprintCallable, Category = "Civic|WorkOrder")
    bool SelectWorkMethod(ECivicWorkMethod Method);

    UFUNCTION(BlueprintCallable, Category = "Civic|WorkOrder")
    bool CompleteWorkOrder(const FCivicWorkOrderOutcome& Outcome);

    UFUNCTION(BlueprintCallable, Category = "Civic|WorkOrder")
    bool AbandonWorkOrder();

    UFUNCTION(BlueprintPure, Category = "Civic|WorkOrder")
    bool HasActiveWorkOrder() const { return bWorkOrderActive; }

    UFUNCTION(BlueprintPure, Category = "Civic|WorkOrder")
    FCivicWorkOrderDefinition GetActiveWorkOrder() const { return ActiveOrder; }

    UFUNCTION(BlueprintPure, Category = "Civic|WorkOrder")
    bool IsAuthorizedWorkZone(FName ZoneId, bool bWearingVest, bool bConesDeployed) const;

    UFUNCTION(BlueprintPure, Category = "Civic|Campaign")
    FCivicCampaignProgress GetCampaignProgress() const { return Progress; }

    UFUNCTION(BlueprintPure, Category = "Civic|Campaign")
    int32 GetDistrictStrain(FName District) const;

    UFUNCTION(BlueprintPure, Category = "Civic|Campaign")
    bool WasWorkOrderCompleted(FName MissionId) const;

    UFUNCTION(BlueprintCallable, Category = "Civic|Campaign")
    bool UnlockWingContact(FName ContactId, bool bMeansWing);

    UFUNCTION(BlueprintCallable, Category = "Civic|Campaign")
    bool UnlockCommitteeProcedure();

    UFUNCTION(BlueprintPure, Category = "Civic|Campaign")
    bool IsEndingEligible(ECivicCampaignEnding Ending) const;

protected:
    virtual bool DoesSupportWorldType(EWorldType::Type WorldType) const override;

private:
    UPROPERTY(Transient)
    FCivicWorkOrderDefinition ActiveOrder;

    UPROPERTY(Transient)
    FCivicCampaignProgress Progress;

    UPROPERTY(Transient)
    TMap<FName, int32> DistrictStrain;

    UPROPERTY(Transient)
    TSet<FName> ResolvedOrderIds;

    UPROPERTY(Transient)
    TSet<FName> BelieverContacts;

    UPROPERTY(Transient)
    TSet<FName> MeansContacts;

    bool bWorkOrderActive = false;
    bool bMethodChosen = false;
    bool bCommitteeProcedureUnlocked = false;
    ECivicWorkMethod ActiveMethod = ECivicWorkMethod::Kind;

    bool CanMutate() const;
};
