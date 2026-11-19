#pragma once

#include <cstdint>

namespace RVA::NightShift
{
enum class Phase : std::uint8_t
{
    Available,
    Briefed,
    Striping,
    Detour,
    ReturnToYard,
    Complete
};

enum class Segment : std::uint8_t { A = 1, B = 2 };
enum class Exit : std::uint8_t { None, Detour, Recovery };

enum class PassStatus { Idle, Painting, Cancelled, Finished };

class StripePass
{
public:
    constexpr bool IsActive() const { return Direction != 0; }

    constexpr bool Arm(double Along)
    {
        if (IsActive() || !(Along >= -1.0 && Along <= 1.0) || (Along > -0.72 && Along < 0.72))
        {
            return false;
        }
        Direction = Along < 0.0 ? 1 : -1;
        return true;
    }

    constexpr PassStatus Sample(double Along, bool InsideLane, bool Authorized)
    {
        if (!IsActive())
        {
            return PassStatus::Idle;
        }
        const double Advance = Along * Direction;
        if (!InsideLane || !Authorized || !(Advance >= -1.14))
        {
            Reset();
            return PassStatus::Cancelled;
        }
        if (Advance >= 0.82)
        {
            Reset();
            return PassStatus::Finished;
        }
        return PassStatus::Painting;
    }

    constexpr void Reset() { Direction = 0; }

private:
    int Direction = 0;
};

struct Checkpoint
{
    Phase Current = Phase::Available;
    std::uint8_t Stripes = 0;
    Exit Route = Exit::None;
};

class Progress
{
public:
    constexpr Checkpoint GetCheckpoint() const { return State; }

    constexpr bool Brief()
    {
        return Advance(Phase::Available, Phase::Briefed);
    }

    constexpr bool BoardTruck()
    {
        return Advance(Phase::Briefed, Phase::Striping);
    }

    constexpr bool HasStripe(Segment Target) const
    {
        return (State.Stripes & static_cast<std::uint8_t>(Target)) != 0;
    }

    constexpr bool Paint(Segment Target)
    {
        const auto Bit = static_cast<std::uint8_t>(Target);
        if (State.Current != Phase::Striping || (Bit != 1 && Bit != 2) || HasStripe(Target))
        {
            return false;
        }
        State.Stripes |= Bit;
        if (State.Stripes == 3)
        {
            State.Current = Phase::Detour;
        }
        return true;
    }

    constexpr bool ClearSite(Exit Route)
    {
        if (State.Current != Phase::Detour || (Route != Exit::Detour && Route != Exit::Recovery))
        {
            return false;
        }
        State.Route = Route;
        State.Current = Phase::ReturnToYard;
        return true;
    }

    constexpr bool Debrief()
    {
        return Advance(Phase::ReturnToYard, Phase::Complete);
    }

    constexpr std::uint8_t EvidenceCount() const
    {
        return State.Current == Phase::Complete ? 2 : 0;
    }

    constexpr bool Restore(Checkpoint Saved)
    {
        if (!IsValid(Saved))
        {
            return false;
        }
        State = Saved;
        return true;
    }

    static constexpr bool IsValid(Checkpoint Saved)
    {
        switch (Saved.Current)
        {
            case Phase::Available:
            case Phase::Briefed:
                return Saved.Stripes == 0 && Saved.Route == Exit::None;
            case Phase::Striping:
                return Saved.Stripes < 3 && Saved.Route == Exit::None;
            case Phase::Detour:
                return Saved.Stripes == 3 && Saved.Route == Exit::None;
            case Phase::ReturnToYard:
            case Phase::Complete:
                return Saved.Stripes == 3 && (Saved.Route == Exit::Detour || Saved.Route == Exit::Recovery);
            default:
                return false;
        }
    }

private:
    Checkpoint State;

    constexpr bool Advance(Phase Before, Phase After)
    {
        if (State.Current != Before)
        {
            return false;
        }
        State.Current = After;
        return true;
    }
};
}
