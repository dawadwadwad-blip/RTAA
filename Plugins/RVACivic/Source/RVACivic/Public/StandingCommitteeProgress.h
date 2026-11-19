#pragma once

#include <cstdint>

namespace RVA::StandingCommittee
{
enum class Stage : std::uint8_t
{
    Available,
    Borrowed,
    Returned
};

class FavorProgress
{
public:
    constexpr Stage GetStage() const { return Current; }

    constexpr bool Borrow()
    {
        if (Current != Stage::Available)
        {
            return false;
        }
        Current = Stage::Borrowed;
        return true;
    }

    constexpr bool Return()
    {
        if (Current != Stage::Borrowed)
        {
            return false;
        }
        Current = Stage::Returned;
        return true;
    }

    constexpr bool LoseBorrower()
    {
        if (Current != Stage::Borrowed)
        {
            return false;
        }
        Current = Stage::Available;
        return true;
    }

private:
    Stage Current = Stage::Available;
};
}
