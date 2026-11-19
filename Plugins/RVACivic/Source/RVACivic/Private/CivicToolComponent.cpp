#include "CivicToolComponent.h"

#include "CivicFactionSubsystem.h"
#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "Components/BoxComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/OverlapResult.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Math/RotationMatrix.h"
#include "PhysicsEngine/PhysicsConstraintComponent.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
const FName PotholeTag(TEXT("CivicPothole"));
const FName TowableTag(TEXT("CivicTowable"));
const FName PlacedWithPermitTag(TEXT("CivicPermittedSite"));
constexpr int32 MaxActiveEffects = 16;
constexpr float CompostRadiusCm = 425.0f;

FLinearColor PatchColor(ECivicTool Tool)
{
    switch (Tool)
    {
        case ECivicTool::LineStriper: return FLinearColor(0.06f, 0.9f, 0.23f);
        case ECivicTool::PotholeCannon: return FLinearColor(0.026f, 0.026f, 0.026f);
        default: return FLinearColor(0.31f, 0.14f, 0.04f);
    }
}

bool IsVehicleOrTowable(const UPrimitiveComponent& Body, const AActor& Actor)
{
    return Body.GetCollisionObjectType() == ECC_Vehicle || Actor.ActorHasTag(TowableTag);
}
}

ACivicToolEffect::ACivicToolEffect()
{
    PrimaryActorTick.bCanEverTick = false;
    Trigger = CreateDefaultSubobject<UBoxComponent>(TEXT("CivicToolTrigger"));
    Trigger->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Trigger->SetCollisionObjectType(ECC_WorldDynamic);
    Trigger->SetCollisionResponseToAllChannels(ECR_Ignore);
    Trigger->SetCollisionResponseToChannel(ECC_Vehicle, ECR_Overlap);
    Trigger->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Overlap);
    Trigger->SetCollisionResponseToChannel(ECC_WorldDynamic, ECR_Overlap);
    Trigger->SetGenerateOverlapEvents(true);
    Trigger->OnComponentBeginOverlap.AddDynamic(this, &ACivicToolEffect::OnTrapOverlap);
    SetRootComponent(Trigger);

    Marker = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CivicMarker"));
    Marker->SetupAttachment(Trigger);
    Marker->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Marker->SetCastShadow(false);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (Cube.Succeeded())
    {
        Marker->SetStaticMesh(Cube.Object);
    }
}

void ACivicToolEffect::ShowPatch(ECivicTool Tool, const FVector& HalfExtent, float Duration, bool bSpeedBump)
{
    Trigger->SetBoxExtent(HalfExtent, false);
    Marker->SetRelativeScale3D(HalfExtent / 50.0);
    if (UMaterialInstanceDynamic* Tint = Marker->CreateDynamicMaterialInstance(0))
    {
        Tint->SetVectorParameterValue(TEXT("Color"), PatchColor(Tool));
    }
    if (bSpeedBump)
    {
        Trigger->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
    }
    SetLifeSpan(Duration);
}

bool ACivicToolEffect::AnchorBody(UPrimitiveComponent& Body, FName Bone)
{
    if (!Body.IsSimulatingPhysics(Bone) || Constraint)
    {
        return false;
    }
    Constraint = NewObject<UPhysicsConstraintComponent>(this, TEXT("CivicAsphaltAnchor"));
    if (!Constraint)
    {
        return false;
    }
    Constraint->SetupAttachment(Trigger);
    AddInstanceComponent(Constraint);
    Constraint->SetLinearXLimit(LCM_Locked, 0.0f);
    Constraint->SetLinearYLimit(LCM_Locked, 0.0f);
    Constraint->SetLinearZLimit(LCM_Locked, 0.0f);
    Constraint->SetAngularSwing1Limit(ACM_Locked, 0.0f);
    Constraint->SetAngularSwing2Limit(ACM_Locked, 0.0f);
    Constraint->SetAngularTwistLimit(ACM_Locked, 0.0f);
    Constraint->RegisterComponent();
    Constraint->SetConstrainedComponents(&Body, Bone, nullptr, NAME_None);
    const bool bAnchored = Constraint->ConstraintInstance.IsValidConstraintInstance();
    if (!bAnchored)
    {
        Constraint->DestroyComponent();
        Constraint = nullptr;
    }
    return bAnchored;
}

void ACivicToolEffect::PaintTarget(UPrimitiveComponent& Body, FName Bone)
{
    AttachToComponent(&Body, FAttachmentTransformRules::KeepWorldTransform, Bone);
}

void ACivicToolEffect::OnTrapOverlap(UPrimitiveComponent*, AActor* OtherActor,
    UPrimitiveComponent* OtherComponent, int32, bool, const FHitResult&)
{
    if (!HasAuthority() || !IsValid(OtherActor) || OtherActor == GetOwner() || !IsValid(OtherComponent)
        || !IsVehicleOrTowable(*OtherComponent, *OtherActor) || !OtherComponent->IsSimulatingPhysics())
    {
        return;
    }
    const TWeakObjectPtr<AActor> Target(OtherActor);
    if (LaunchedActors.Contains(Target))
    {
        return;
    }
    const FVector Velocity = OtherComponent->GetPhysicsLinearVelocity();
    const double ForwardSpeed = FMath::Abs(FVector::DotProduct(Velocity, GetActorForwardVector()));
    if (ForwardSpeed < 1000.0)
    {
        return;
    }
    LaunchedActors.Add(Target);
    const double Mass = FMath::Clamp(static_cast<double>(OtherComponent->GetMass()), 1.0, 3500.0);
    const double Lift = FMath::Clamp(ForwardSpeed * 0.33, 300.0, 900.0);
    OtherComponent->AddImpulseAtLocation(FVector::UpVector * Lift * Mass, OtherComponent->GetCenterOfMass());
}

UCivicToolComponent::UCivicToolComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
}

ACivicToolEffect* UCivicToolComponent::SpawnEffect(const FHitResult& Hit, const FVector& AimDirection)
{
    const FVector Normal = Hit.ImpactNormal.GetSafeNormal();
    FVector Forward = FVector::VectorPlaneProject(AimDirection, Normal).GetSafeNormal();
    if (Forward.IsNearlyZero())
    {
        FVector Side;
        Normal.FindBestAxisVectors(Forward, Side);
    }
    const FRotator Rotation = FRotationMatrix::MakeFromXZ(Forward, Normal).Rotator();
    FActorSpawnParameters Spawn;
    Spawn.Owner = GetOwner();
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    ACivicToolEffect* Effect = GetWorld()->SpawnActor<ACivicToolEffect>(
        Hit.ImpactPoint + Normal * 4.0, Rotation, Spawn);
    if (Effect)
    {
        Effects.RemoveAll([](const TWeakObjectPtr<ACivicToolEffect>& Item) { return !Item.IsValid(); });
        if (Effects.Num() >= MaxActiveEffects)
        {
            Effects[0]->Destroy();
            Effects.RemoveAt(0);
        }
        Effects.Add(Effect);
    }
    return Effect;
}

bool UCivicToolComponent::UseTool(ECivicTool Tool, FVector AimDirection, FCivicToolResult& Result)
{
    Result = FCivicToolResult();
    AActor* Owner = GetOwner();
    UWorld* World = GetWorld();
    if (!World || !IsValid(Owner) || !Owner->HasAuthority() || World->GetNetMode() == NM_Client
        || AimDirection.ContainsNaN() || !FMath::IsFinite(RangeCm)
        || !StaticEnum<ECivicTool>()->IsValidEnumValue(static_cast<int64>(Tool)))
    {
        return false;
    }
    const FVector Aim = AimDirection.GetSafeNormal();
    const double Time = World->GetTimeSeconds();
    if (Aim.IsNearlyZero() || Time < NextUseTime)
    {
        return false;
    }

    FVector Start;
    FRotator EyeRotation;
    Owner->GetActorEyesViewPoint(Start, EyeRotation);
    FHitResult Hit;
    const FCollisionQueryParams Trace(SCENE_QUERY_STAT(CivicToolAim), false, Owner);
    if (!World->LineTraceSingleByChannel(
        Hit, Start, Start + Aim * FMath::Clamp(RangeCm, 100.0f, 3000.0f), AimChannel, Trace)
        || !Hit.bBlockingHit || Hit.ImpactNormal.IsNearlyZero())
    {
        return false;
    }

    Result.Tool = Tool;
    Result.ImpactLocation = Hit.ImpactPoint;
    const double PreviousUseTime = NextUseTime;
    NextUseTime = Time + (Tool == ECivicTool::CompostLauncher ? 1.0 : 0.5);
    if (!ApplyTool(Tool, Hit, Aim, Result))
    {
        NextUseTime = PreviousUseTime;
        Result = FCivicToolResult();
        return false;
    }
    const AActor* Site = Hit.GetActor();
    if (!Site || !Site->ActorHasTag(PlacedWithPermitTag))
    {
        if (UCivicFactionSubsystem* Factions = World->GetSubsystem<UCivicFactionSubsystem>())
        {
            if (!Factions->GetCityState().bPermitsAvailable)
            {
                Factions->AddRedTapeHeat(Tool == ECivicTool::CompostLauncher ? 8 : 4);
            }
        }
    }
    OnToolApplied.Broadcast(Result);
    return true;
}

bool UCivicToolComponent::ApplyTool(ECivicTool Tool, const FHitResult& Hit, const FVector& Aim, FCivicToolResult& Result)
{
    UPrimitiveComponent* Body = Hit.GetComponent();
    AActor* Target = Hit.GetActor();
    const bool bVehicle = IsValid(Body) && IsValid(Target) && IsVehicleOrTowable(*Body, *Target);
    const bool bGround = Hit.ImpactNormal.Z >= 0.65;
    switch (Tool)
    {
        case ECivicTool::LineStriper:
        {
            if (!bGround && !bVehicle)
            {
                return false;
            }
            ACivicToolEffect* Effect = SpawnEffect(Hit, Aim);
            if (!Effect)
            {
                return false;
            }
            Effect->ShowPatch(Tool, bVehicle ? FVector(18, 30, 2) : FVector(37, 135, 10), 18.0f, !bVehicle);
            if (bVehicle)
            {
                Effect->PaintTarget(*Body, Hit.BoneName);
                Result.AffectedActors = 1;
            }
            return true;
        }
        case ECivicTool::PotholeCannon:
        {
            if (!bGround && !bVehicle)
            {
                return false;
            }
            ACivicToolEffect* Effect = SpawnEffect(Hit, Aim);
            if (!Effect)
            {
                return false;
            }
            if (bVehicle && !Effect->AnchorBody(*Body, Hit.BoneName))
            {
                Effect->Destroy();
                return false;
            }
            if (bVehicle)
            {
                Result.AffectedActors = 1;
            }
            else if (IsValid(Target) && Target->ActorHasTag(PotholeTag))
            {
                Target->SetActorEnableCollision(false);
                Target->SetActorHiddenInGame(true);
                Result.bRepairedPothole = true;
                Result.AffectedActors = 1;
            }
            Effect->ShowPatch(Tool, FVector(55, 48, 5), bVehicle ? 5.0f : 24.0f, false);
            return true;
        }
        case ECivicTool::CompostLauncher:
        {
            ACivicToolEffect* Effect = SpawnEffect(Hit, Aim);
            if (!Effect)
            {
                return false;
            }
            Effect->ShowPatch(Tool, FVector(35, 35, 9), 6.0f, false);
            Result.AffectedActors = ApplyCompostImpulse(Hit);
            return true;
        }
        default:
            return false;
    }
}

int32 UCivicToolComponent::ApplyCompostImpulse(const FHitResult& Hit) const
{
    UWorld* World = GetWorld();
    const FVector Center = Hit.ImpactPoint + Hit.ImpactNormal * 12.0;
    FCollisionObjectQueryParams Objects;
    Objects.AddObjectTypesToQuery(ECC_PhysicsBody);
    Objects.AddObjectTypesToQuery(ECC_Vehicle);
    Objects.AddObjectTypesToQuery(ECC_Pawn);
    Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
    FCollisionQueryParams Trace(SCENE_QUERY_STAT(CivicCompost), false, GetOwner());
    TArray<FOverlapResult> Overlaps;
    World->OverlapMultiByObjectType(Overlaps, Center, FQuat::Identity, Objects,
        FCollisionShape::MakeSphere(CompostRadiusCm), Trace);

    TSet<AActor*> HitActors;
    // Prefer a physics root when an actor has several overlapping components.
    for (const FOverlapResult& Overlap : Overlaps)
    {
        AActor* Actor = Overlap.GetActor();
        UPrimitiveComponent* Body = Overlap.GetComponent();
        if (!IsValid(Actor) || !IsValid(Body) || HitActors.Contains(Actor))
        {
            continue;
        }
        if (UPrimitiveComponent* RootBody = Cast<UPrimitiveComponent>(Actor->GetRootComponent()))
        {
            if (RootBody->IsSimulatingPhysics())
            {
                Body = RootBody;
            }
        }
        const FVector Target = Body->Bounds.Origin;
        FHitResult Blocker;
        if (World->LineTraceSingleByChannel(Blocker, Center, Target, AimChannel, Trace)
            && Blocker.GetActor() != Actor)
        {
            continue;
        }
        const double Distance = FVector::Distance(Center, Target);
        if (Distance >= CompostRadiusCm)
        {
            continue;
        }
        const double Strength = 1.0 - Distance / CompostRadiusCm;
        const FVector Kick = ((Target - Center).GetSafeNormal() + FVector::UpVector * 0.55).GetSafeNormal()
            * (920.0 * Strength);
        if (Body->IsSimulatingPhysics())
        {
            const double Mass = FMath::Clamp(static_cast<double>(Body->GetMass()), 1.0, 3500.0);
            Body->AddImpulseAtLocation(Kick * Mass, Body->GetCenterOfMass());
        }
        else if (ACharacter* Character = Cast<ACharacter>(Actor))
        {
            if (UCharacterMovementComponent* Movement = Character->GetCharacterMovement())
            {
                Movement->AddImpulse(Kick, true);
            }
            else
            {
                continue;
            }
        }
        else
        {
            continue;
        }
        HitActors.Add(Actor);
    }
    return HitActors.Num();
}

void UCivicToolComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    for (const TWeakObjectPtr<ACivicToolEffect>& Effect : Effects)
    {
        if (Effect.IsValid())
        {
            Effect->Destroy();
        }
    }
    Effects.Reset();
    Super::EndPlay(EndPlayReason);
}
