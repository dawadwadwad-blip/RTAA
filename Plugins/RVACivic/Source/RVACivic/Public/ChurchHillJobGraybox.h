#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ChurchHillJobProgress.h"
#include "ChurchHillJobGraybox.generated.h"

class APawn;
class APlayerController;
class UBoxComponent;
class UStaticMeshComponent;
class UTextRenderComponent;

UCLASS(Abstract, BlueprintType)
class RVACIVIC_API AChurchHillJobGraybox : public AActor
{
    GENERATED_BODY()

public:
    AChurchHillJobGraybox();
    virtual void Tick(float DeltaSeconds) override;
    void SetSliceEnabled(bool bEnabled) { bSliceEnabled = bEnabled; }

    UPROPERTY(EditInstanceOnly, Category = "Church Hill|Input")
    bool bBindTestKey = true;

    UFUNCTION(BlueprintCallable, Category = "Church Hill")
    bool PerformObjective(APawn* Pawn);

    UFUNCTION(BlueprintPure, Category = "Church Hill")
    bool IsComplete() const { return bCompleted; }

protected:
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

    UBoxComponent* MakeZone(FName Name, const FVector& Center);
    UTextRenderComponent* MakeSign(FName Name, USceneComponent& Parent, const FVector& RelativePosition);
    UStaticMeshComponent* MakeProp(FName Name, USceneComponent& Parent, const FVector& Dimensions);
    static bool Contains(const UBoxComponent& Zone, const APawn& Pawn);
    static double SpeedMps(const APawn& Pawn);
    void MarkComplete() { bCompleted = true; }

    virtual bool Advance(APawn& Pawn) PURE_VIRTUAL(AChurchHillJobGraybox::Advance, return false;);
    virtual void UpdateJob(APawn*, float) {}

private:
    TWeakObjectPtr<APlayerController> TestController;
    bool bBound = false;
    bool bCompleted = false;
    bool bSliceEnabled = true;

    bool IsLocalPawn(const APawn* Pawn) const;
    void BindTestKey(APlayerController* Controller);
    void HandleTestKey();
};

UENUM(BlueprintType)
enum class EChurchHillRoute : uint8
{
    Unset,
    Gentle,
    Direct
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FHillClimbDelivered, EChurchHillRoute, Route);

UCLASS(BlueprintType)
class RVACIVIC_API AHillClimbGraybox final : public AChurchHillJobGraybox
{
    GENERATED_BODY()

public:
    AHillClimbGraybox();
    virtual void OnConstruction(const FTransform& Transform) override;

    UPROPERTY(EditInstanceOnly, Category = "Hill Climb")
    FName TruckTag{TEXT("NightShiftTruck")};

    UPROPERTY(EditInstanceOnly, Category = "Hill Climb")
    FVector CargoOffsetCm = FVector(-120, 0, 150);

    UPROPERTY(BlueprintAssignable, Category = "Hill Climb")
    FHillClimbDelivered OnDelivered;

    UFUNCTION(BlueprintPure, Category = "Hill Climb")
    EChurchHillRoute GetRoute() const;

    UFUNCTION(BlueprintPure, Category = "Hill Climb")
    FText GetObjective() const;

protected:
    virtual void BeginPlay() override;
    virtual bool Advance(APawn& Pawn) override;
    virtual void UpdateJob(APawn* Pawn, float DeltaSeconds) override;

private:
    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Placement")
    TObjectPtr<UBoxComponent> Pickup;

    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Placement")
    TObjectPtr<UBoxComponent> GentleGate;

    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Placement")
    TObjectPtr<UBoxComponent> DirectGate;

    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Placement")
    TObjectPtr<UBoxComponent> Warning;

    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Placement")
    TObjectPtr<UBoxComponent> PullOff;

    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Placement")
    TObjectPtr<UBoxComponent> Delivery;

    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Placement")
    TObjectPtr<UStaticMeshComponent> Cornice;

    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Presentation")
    TObjectPtr<UTextRenderComponent> PickupSign;

    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Presentation")
    TObjectPtr<UTextRenderComponent> PullOffSign;

    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Presentation")
    TObjectPtr<UTextRenderComponent> WarningSign;

    UPROPERTY(VisibleAnywhere, Category = "Hill Climb|Presentation")
    TObjectPtr<UTextRenderComponent> DeliverySign;

    RVA::ChurchHill::HillClimbProgress Progress;
    TWeakObjectPtr<APawn> CargoTruck;

    void ParkCornice(UBoxComponent& Site);
    void RefreshSigns();
};

UENUM(BlueprintType)
enum class ESurveyStakesMethod : uint8
{
    None,
    Kind,
    Hard
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FSurveyStakesResolved, ESurveyStakesMethod, Method);

UCLASS(BlueprintType)
class RVACIVIC_API ASurveyStakesGraybox final : public AChurchHillJobGraybox
{
    GENERATED_BODY()

public:
    ASurveyStakesGraybox();
    virtual void OnConstruction(const FTransform& Transform) override;

    UPROPERTY(EditInstanceOnly, Category = "Survey Stakes", meta = (ClampMin = "5.0", ClampMax = "300.0"))
    float HardTimeLimitSeconds = 40.0f;

    UPROPERTY(BlueprintAssignable, Category = "Survey Stakes")
    FSurveyStakesResolved OnResolved;

    UFUNCTION(BlueprintPure, Category = "Survey Stakes")
    ESurveyStakesMethod GetMethod() const;

    UFUNCTION(BlueprintPure, Category = "Survey Stakes")
    bool IsDeliveryDiverted() const;

protected:
    virtual void BeginPlay() override;
    virtual bool Advance(APawn& Pawn) override;
    virtual void UpdateJob(APawn* Pawn, float DeltaSeconds) override;

private:
    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Placement")
    TObjectPtr<UBoxComponent> KindBrief;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Placement")
    TObjectPtr<UBoxComponent> HardBrief;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Placement")
    TObjectPtr<UBoxComponent> SiteA;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Placement")
    TObjectPtr<UBoxComponent> SiteB;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Placement")
    TObjectPtr<UStaticMeshComponent> StakeA;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Placement")
    TObjectPtr<UStaticMeshComponent> StakeB;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Presentation")
    TObjectPtr<UTextRenderComponent> BoardA;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Presentation")
    TObjectPtr<UTextRenderComponent> BoardB;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Presentation")
    TObjectPtr<UTextRenderComponent> KindSign;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Presentation")
    TObjectPtr<UTextRenderComponent> HardSign;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Presentation")
    TObjectPtr<UTextRenderComponent> LoadingSign;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Placement")
    TObjectPtr<UBoxComponent> LoadingGate;

    UPROPERTY(VisibleAnywhere, Category = "Survey Stakes|Presentation")
    TObjectPtr<UStaticMeshComponent> LoadingBarrier;

    RVA::ChurchHill::SurveyStakesProgress Progress;
    int32 LastSecondsShown = -1;
    bool bTimedOut = false;

    void RefreshWorld();
};
