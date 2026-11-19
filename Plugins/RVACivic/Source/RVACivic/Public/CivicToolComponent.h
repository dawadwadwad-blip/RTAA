#pragma once

#include "Components/ActorComponent.h"
#include "CoreMinimal.h"
#include "Engine/EngineTypes.h"
#include "GameFramework/Actor.h"
#include "CivicToolComponent.generated.h"

class UBoxComponent;
class UPhysicsConstraintComponent;
class UPrimitiveComponent;
class UStaticMeshComponent;

UENUM(BlueprintType)
enum class ECivicTool : uint8
{
    LineStriper,
    PotholeCannon,
    CompostLauncher
};

USTRUCT(BlueprintType)
struct RVACIVIC_API FCivicToolResult
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    ECivicTool Tool = ECivicTool::LineStriper;

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    FVector ImpactLocation = FVector::ZeroVector;

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    int32 AffectedActors = 0;

    UPROPERTY(BlueprintReadOnly, Category = "Civic")
    bool bRepairedPothole = false;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FCivicToolApplied, const FCivicToolResult&, Result);

UCLASS(NotBlueprintable)
class RVACIVIC_API ACivicToolEffect final : public AActor
{
    GENERATED_BODY()

public:
    ACivicToolEffect();
    void ShowPatch(ECivicTool Tool, const FVector& HalfExtent, float Duration, bool bSpeedBump);
    bool AnchorBody(UPrimitiveComponent& Body, FName Bone);
    void PaintTarget(UPrimitiveComponent& Body, FName Bone);

private:
    UPROPERTY(VisibleAnywhere, Category = "Civic")
    TObjectPtr<UBoxComponent> Trigger;

    UPROPERTY(VisibleAnywhere, Category = "Civic")
    TObjectPtr<UStaticMeshComponent> Marker;

    UPROPERTY(Transient)
    TObjectPtr<UPhysicsConstraintComponent> Constraint;

    TSet<TWeakObjectPtr<AActor>> LaunchedActors;

    UFUNCTION()
    void OnTrapOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor,
        UPrimitiveComponent* OtherComponent, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);
};

UCLASS(BlueprintType, ClassGroup = (Civic), meta = (BlueprintSpawnableComponent))
class RVACIVIC_API UCivicToolComponent final : public UActorComponent
{
    GENERATED_BODY()

public:
    UCivicToolComponent();

    UPROPERTY(BlueprintAssignable, Category = "Civic|Events")
    FCivicToolApplied OnToolApplied;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|Tools", meta = (ClampMin = "100", ClampMax = "3000"))
    float RangeCm = 1600.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Civic|Tools")
    TEnumAsByte<ECollisionChannel> AimChannel = ECC_Visibility;

    UFUNCTION(BlueprintCallable, Category = "Civic|Tools")
    bool UseTool(ECivicTool Tool, FVector AimDirection, FCivicToolResult& Result);

protected:
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    double NextUseTime = 0;
    TArray<TWeakObjectPtr<ACivicToolEffect>> Effects;

    ACivicToolEffect* SpawnEffect(const FHitResult& Hit, const FVector& AimDirection);
    bool ApplyTool(ECivicTool Tool, const FHitResult& Hit, const FVector& Aim, FCivicToolResult& Result);
    int32 ApplyCompostImpulse(const FHitResult& Hit) const;
};
