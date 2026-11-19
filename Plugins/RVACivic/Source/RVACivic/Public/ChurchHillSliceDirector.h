#pragma once

#include "ChurchHillJobGraybox.h"
#include "ChurchHillSliceSequence.h"
#include "CivicWorkOrderSubsystem.h"
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ChurchHillSliceDirector.generated.h"

class ANightShiftWorkOrder;
class APawn;
class UTextRenderComponent;

UCLASS(BlueprintType)
class RVACIVIC_API AChurchHillSliceDirector final : public AActor
{
    GENERATED_BODY()

public:
    AChurchHillSliceDirector();
    virtual void Tick(float DeltaSeconds) override;

    UPROPERTY(EditInstanceOnly, Category = "Slice")
    TObjectPtr<ANightShiftWorkOrder> NightShift;

    UPROPERTY(EditInstanceOnly, Category = "Slice")
    TObjectPtr<AHillClimbGraybox> HillClimb;

    UPROPERTY(EditInstanceOnly, Category = "Slice")
    TObjectPtr<ASurveyStakesGraybox> SurveyStakes;

    UPROPERTY(EditInstanceOnly, Category = "Slice|Playtest")
    TSubclassOf<APawn> PlaytestTruckClass;

    UPROPERTY(EditInstanceOnly, Category = "Slice|Outcomes")
    FCivicWorkOrderOutcome NightOutcome;

    UPROPERTY(EditInstanceOnly, Category = "Slice|Outcomes")
    FCivicWorkOrderOutcome HillGentleOutcome;

    UPROPERTY(EditInstanceOnly, Category = "Slice|Outcomes")
    FCivicWorkOrderOutcome HillDirectOutcome;

    UPROPERTY(EditInstanceOnly, Category = "Slice|Outcomes")
    FCivicWorkOrderOutcome SurveyKindOutcome;

    UPROPERTY(EditInstanceOnly, Category = "Slice|Outcomes")
    FCivicWorkOrderOutcome SurveyHardOutcome;

    UFUNCTION(BlueprintCallable, Category = "Slice")
    bool RefreshSlice();

    UFUNCTION(BlueprintPure, Category = "Slice")
    FName GetCurrentMissionId() const;

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    UPROPERTY(VisibleAnywhere, Category = "Slice")
    TObjectPtr<UTextRenderComponent> ProgressSign;

    UPROPERTY(Transient)
    TObjectPtr<UCivicWorkOrderSubsystem> Ledger;

    RVA::Slice::Sequence Jobs;
    TWeakObjectPtr<APawn> TaggedPawn;
    TOptional<ECivicWorkMethod> PendingMethod;
    bool bOwnsActiveOrder = false;
    bool bMethodSelected = false;
    bool bRefreshing = false;
    bool bHillDirect = false;

    void EnableOnly(RVA::Slice::Job Job);
    bool EnsureOrder();
    const FCivicWorkOrderOutcome& OutcomeFor(RVA::Slice::Job Job) const;

    UFUNCTION()
    void HandleNight();
    UFUNCTION()
    void HandleHill(EChurchHillRoute Route);
    UFUNCTION()
    void HandleSurvey(ESurveyStakesMethod Method);
};
