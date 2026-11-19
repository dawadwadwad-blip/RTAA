#include "StandingCommitteeSkeleton.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Math/RotationMatrix.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
constexpr double SkeletonScale = 609.6 / 600.0;

void AddPiece(UInstancedStaticMeshComponent& Mesh, const FVector& Center, const FVector& Dimensions,
    const FQuat& Rotation = FQuat::Identity)
{
    // The built-in primitives have 100 cm nominal dimensions.
    Mesh.AddInstance(FTransform(Rotation, Center * SkeletonScale, Dimensions * (SkeletonScale / 100.0)));
}

void AddBone(UInstancedStaticMeshComponent& Mesh, const FVector& Start, const FVector& End, double Radius)
{
    const FVector Axis = End - Start;
    AddPiece(Mesh, (Start + End) * 0.5, FVector(2 * Radius, 2 * Radius, Axis.Size()),
        FRotationMatrix::MakeFromZ(Axis).ToQuat());
}

void Tint(UInstancedStaticMeshComponent& Mesh, const FLinearColor& Color)
{
    UMaterialInstanceDynamic* Material = Cast<UMaterialInstanceDynamic>(Mesh.GetMaterial(0));
    if (!Material)
    {
        Material = Mesh.CreateDynamicMaterialInstance(0);
    }
    if (Material)
    {
        Material->SetVectorParameterValue(TEXT("Color"), Color);
    }
}
}

AStandingCommitteeSkeleton::AStandingCommitteeSkeleton()
{
    PrimaryActorTick.bCanEverTick = false;
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("SkeletonBase")));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));

    Bones = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Bones"));
    RoundedBones = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("RoundedBones"));
    EyeSockets = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("EyeSockets"));
    Fabric = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("SignalFabric"));
    Metal = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("StandAndChair"));
    const auto Setup = [this](UInstancedStaticMeshComponent& Mesh, UStaticMesh* Shape)
    {
        Mesh.SetupAttachment(GetRootComponent());
        Mesh.SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Mesh.SetGenerateOverlapEvents(false);
        Mesh.SetStaticMesh(Shape);
    };
    Setup(*Bones, Cylinder.Object);
    Setup(*RoundedBones, Sphere.Object);
    Setup(*EyeSockets, Sphere.Object);
    Setup(*Fabric, Cube.Object);
    Setup(*Metal, Cube.Object);
}

void AStandingCommitteeSkeleton::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    Rebuild();
}

void AStandingCommitteeSkeleton::BeginPlay()
{
    Super::BeginPlay();
    Rebuild();
}

void AStandingCommitteeSkeleton::SetSignal(EStandingCommitteeSignal NewSignal)
{
    if (Signal == NewSignal || !StaticEnum<EStandingCommitteeSignal>()->IsValidEnumValue(static_cast<int64>(NewSignal)))
    {
        return;
    }
    Signal = NewSignal;
    Rebuild();
}

void AStandingCommitteeSkeleton::Rebuild()
{
    Bones->ClearInstances();
    RoundedBones->ClearInstances();
    EyeSockets->ClearInstances();
    Fabric->ClearInstances();
    Metal->ClearInstances();
    const FLinearColor Plastic(0.83f, 0.75f, 0.56f);
    Tint(*Bones, Plastic);
    Tint(*RoundedBones, Plastic);
    Tint(*EyeSockets, FLinearColor(0.015f, 0.012f, 0.01f));
    Tint(*Fabric, Signal == EStandingCommitteeSignal::SafetyVest
        ? FLinearColor(1.0f, 0.23f, 0.025f) : FLinearColor(0.035f, 0.24f, 0.62f));
    Tint(*Metal, FLinearColor(0.08f, 0.08f, 0.08f));

    AddPiece(*Metal, FVector(0, 0, 3), FVector(100, 84, 6));
    AddPiece(*RoundedBones, FVector(0, 0, 550), FVector(76, 87, 100));
    AddPiece(*RoundedBones, FVector(14, 0, 506), FVector(66, 66, 35));
    AddPiece(*EyeSockets, FVector(31, 20, 560), FVector(19, 25, 25));
    AddPiece(*EyeSockets, FVector(31, -20, 560), FVector(19, 25, 25));
    AddPiece(*EyeSockets, FVector(37, 0, 535), FVector(12, 16, 13));
    for (int32 Tooth = -3; Tooth <= 3; ++Tooth)
    {
        AddPiece(*RoundedBones, FVector(42, Tooth * 7, 518), FVector(9, 6, 13));
    }

    AddBone(*Bones, FVector(-16, 0, 236), FVector(-16, 0, 508), 9.0);
    for (int32 Spine = 0; Spine < 12; ++Spine)
    {
        AddPiece(*RoundedBones, FVector(-18, 0, 247 + 18 * Spine), FVector(27, 32, 17));
    }
    AddBone(*Bones, FVector(30, 0, 326), FVector(31, 0, 455), 7.5);
    for (int32 Rib = 0; Rib < 6; ++Rib)
    {
        const double Width = 49.0 - 3.8 * Rib;
        const double Height = 448.0 - 20.0 * Rib;
        for (int32 Side : {-1, 1})
        {
            FVector Previous(-18, 0, Height);
            for (int32 Segment = 1; Segment <= 9; ++Segment)
            {
                const double Angle = UE_DOUBLE_PI * Segment / 9.0;
                const FVector Position(7 - 25 * FMath::Cos(Angle),
                    Side * Width * FMath::Sin(Angle), Height - 17 * (1 - FMath::Cos(Angle)));
                AddBone(*Bones, Previous, Position, 3.7);
                Previous = Position;
            }
        }
    }
    AddPiece(*RoundedBones, FVector(-1, 0, 248), FVector(55, 87, 43));
    for (int32 Side : {-1, 1})
    {
        const FVector Shoulder(0, Side * 56, 469);
        const FVector Elbow(-5, Side * 72, 361);
        const FVector Wrist(16, Side * 70, 272);
        const FVector Hip(0, Side * 28, 234);
        const FVector Knee(2, Side * 30, 124);
        const FVector Ankle(1, Side * 34, 18);
        AddBone(*Bones, FVector(-7, 0, 475), Shoulder, 7);
        AddBone(*Bones, Shoulder, Elbow, 8);
        AddBone(*Bones, Elbow, Wrist, 5.8);
        AddBone(*Bones, Elbow + FVector(0, Side * 8, 0), Wrist + FVector(0, Side * 7, 0), 4);
        AddBone(*Bones, Hip, Knee, 11);
        AddBone(*Bones, Knee, Ankle, 8);
        AddBone(*Bones, Knee + FVector(-5, Side * 8, 0), Ankle + FVector(-4, Side * 7, 0), 4.0);
        for (const FVector& Joint : {Shoulder, Elbow, Wrist, Hip, Knee, Ankle})
        {
            AddPiece(*RoundedBones, Joint, FVector(21, 23, 24));
        }
        AddPiece(*RoundedBones, Wrist - FVector(0, 0, 12), FVector(19, 31, 31));
        for (int32 Finger = -1; Finger < 3; ++Finger)
        {
            const FVector Knuckle = Wrist + FVector(0, Finger * 6, -20);
            AddBone(*Bones, Knuckle, Knuckle + FVector(3, 0, -20), 2.5);
        }
        AddPiece(*RoundedBones, Ankle + FVector(13, 0, -6), FVector(59, 32, 19));
    }

    if (Signal == EStandingCommitteeSignal::SafetyVest)
    {
        const FQuat Slope(FVector::RightVector, FMath::DegreesToRadians(-8.0));
        for (int32 Side : {-1, 1})
        {
            AddPiece(*Fabric, FVector(35, Side * 30, 420), FVector(6, 33, 97), Slope);
            AddPiece(*Fabric, FVector(0, Side * 31, 466), FVector(67, 28, 7));
            AddPiece(*Metal, FVector(39, Side * 30, 397), FVector(3, 34, 5));
        }
    }
    else if (Signal == EStandingCommitteeSignal::MeetingChair)
    {
        AddPiece(*Fabric, FVector(80, 75, 44), FVector(41, 43, 4));
        AddPiece(*Fabric, FVector(60, 75, 68), FVector(4, 43, 43));
        for (int32 Side : {-1, 1})
        {
            const double Y = 75 + Side * 19;
            const FQuat Forward(FVector::RightVector, FMath::DegreesToRadians(17.0));
            const FQuat Backward(FVector::RightVector, FMath::DegreesToRadians(-17.0));
            AddPiece(*Metal, FVector(79, Y, 24), FVector(4, 4, 46), Forward);
            AddPiece(*Metal, FVector(79, Y, 24), FVector(4, 4, 46), Backward);
        }
    }
}
