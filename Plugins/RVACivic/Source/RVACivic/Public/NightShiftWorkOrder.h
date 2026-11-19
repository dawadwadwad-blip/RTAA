#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/SaveGame.h"
#include "NightShiftProgress.h"
#include "NightShiftWorkOrder.generated.h"

class APlayerController;
class APawn;
class UBoxComponent;
class UPointLightComponent;
class USceneComponent;
class UStaticMeshComponent;
class UTextRenderComponent;

UENUM(BlueprintType)
enum class ENightShiftPhase : uint8
{
    Available,
    Briefed,
    Striping,
    Detour,
    ReturnToYard,
    Complete
};

UENUM(BlueprintType)
enum class ENightShiftExit : uint8
{
    None,
    Detour,
    Recovery
};

USTRUCT(BlueprintType)
struct RVACIVIC_API FNightShiftEvidence
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Night Shift")
    FName DispatchStub;

    UPROPERTY(BlueprintReadOnly, Category = "Night Shift")
    FName LogEntry;

    UPROPERTY(BlueprintReadOnly, Category = "Night Shift")
    ENightShiftExit ExitTaken = ENightShiftExit::None;

    UPROPERTY(BlueprintReadOnly, Category = "Night Shift")
    FVector ExitLocation = FVector::ZeroVector;

    UPROPERTY(BlueprintReadOnly, Category = "Night Shift")
    double TruckExitSeconds = 0.0;
};

UCLASS()
class RVACIVIC_API UNightShiftCheckpoint final : public USaveGame
{
    GENERATED_BODY()

public:
    UPROPERTY(SaveGame)
    int32 Version = 0;

    UPROPERTY(SaveGame)
    uint8 Phase = 0;

    UPROPERTY(SaveGame)
    uint8 Stripes = 0;

    UPROPERTY(SaveGame)
    uint8 Route = 0;

    UPROPERTY(SaveGame)
    FVector ExitLocation = FVector::ZeroVector;

    UPROPERTY(SaveGame)
    double TruckExitSeconds = 0.0;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FNightShiftChanged, ENightShiftPhase, Phase);
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FNightShiftEvent);

UCLASS(BlueprintType)
class RVACIVIC_API ANightShiftWorkOrder final : public AActor
{
    GENERATED_BODY()

public:
    ANightShiftWorkOrder();
    virtual void OnConstruction(const FTransform& Transform) override;
    virtual void Tick(float DeltaSeconds) override;
    void SetSliceEnabled(bool bEnabled) { bSliceEnabled = bEnabled; }

    UPROPERTY(EditInstanceOnly, Category = "Night Shift")
    FName TruckTag{TEXT("NightShiftTruck")};

    UPROPERTY(EditInstanceOnly, Category = "Night Shift")
    bool bShowTestSurface = true;

    UPROPERTY(EditInstanceOnly, Category = "Night Shift")
    bool bBindTestKeys = true;

    UPROPERTY(EditInstanceOnly, Category = "Night Shift|Checkpoint")
    bool bPersistCheckpoint = false;

    UPROPERTY(EditInstanceOnly, Category = "Night Shift|Checkpoint")
    FName CheckpointId{TEXT("ChurchHillBlock")};

    UPROPERTY(BlueprintAssignable, Category = "Night Shift")
    FNightShiftChanged OnProgressChanged;

    UPROPERTY(BlueprintAssignable, Category = "Night Shift")
    FNightShiftEvent OnClosure;

    UPROPERTY(BlueprintAssignable, Category = "Night Shift")
    FNightShiftEvent OnDebriefCompleted;

    UFUNCTION(BlueprintPure, Category = "Night Shift")
    ENightShiftPhase GetPhase() const;

    UFUNCTION(BlueprintPure, Category = "Night Shift")
    FText GetObjective() const;

    UFUNCTION(BlueprintPure, Category = "Night Shift")
    bool IsInAuthorizedWorkZone() const { return bInsideWorkZone; }

    UFUNCTION(BlueprintPure, Category = "Night Shift")
    bool GetEvidence(FNightShiftEvidence& OutEvidence) const;

    UFUNCTION(BlueprintCallable, Category = "Night Shift")
    bool PerformObjective(APawn* Pawn);

    UFUNCTION(BlueprintCallable, Category = "Night Shift")
    bool RetryCheckpoint(APawn* Pawn);

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Placement")
    TObjectPtr<UBoxComponent> Yard;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Placement")
    TObjectPtr<UBoxComponent> WorkZone;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Placement")
    TObjectPtr<UBoxComponent> StripeA;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Placement")
    TObjectPtr<UBoxComponent> StripeB;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Placement")
    TObjectPtr<UBoxComponent> DetourExit;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Placement")
    TObjectPtr<UBoxComponent> RecoveryExit;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Placement")
    TObjectPtr<UBoxComponent> MainExitBarrier;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Placement")
    TObjectPtr<USceneComponent> WorkCheckpoint;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Placement")
    TObjectPtr<USceneComponent> YardCheckpoint;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Presentation")
    TObjectPtr<UStaticMeshComponent> TestSurface;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Presentation")
    TObjectPtr<UStaticMeshComponent> BarrierMesh;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Presentation")
    TObjectPtr<UStaticMeshComponent> PaintedA;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Presentation")
    TObjectPtr<UStaticMeshComponent> PaintedB;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Presentation")
    TObjectPtr<UPointLightComponent> ClosureLight;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Presentation")
    TObjectPtr<UTextRenderComponent> ObjectiveSign;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Presentation")
    TObjectPtr<UTextRenderComponent> WorkZoneSign;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Presentation")
    TObjectPtr<UTextRenderComponent> DetourSign;

    UPROPERTY(VisibleAnywhere, Category = "Night Shift|Presentation")
    TObjectPtr<UTextRenderComponent> RecoverySign;

    RVA::NightShift::Progress Order;
    RVA::NightShift::Checkpoint LastCheckpoint;
    TWeakObjectPtr<APlayerController> TestController;
    TWeakObjectPtr<APlayerController> OwnerController;
    FVector TruckExitLocation = FVector::ZeroVector;
    double TruckExitSeconds = 0.0;
    uint8 PaintingBit = 0;
    RVA::NightShift::StripePass ActivePass;
    bool bInsideWorkZone = false;
    bool bKeysBound = false;
    bool bSliceEnabled = true;

    bool IsPlayerPawn(const APawn* Pawn) const;
    bool IsWorkTruck(const APawn& Pawn) const;
    bool StartStripe(const APawn& Pawn);
    void UpdateStripe(const APawn& Pawn);
    void CancelStripe();
    void CommitProgress();
    void RefreshWorld();
    void BindTestKeys();
    FString GetCheckpointSlot() const;
    void SaveCheckpoint();
    void LoadCheckpoint();

    void HandleObjectiveKey();
    void HandleRetryKey();
};
