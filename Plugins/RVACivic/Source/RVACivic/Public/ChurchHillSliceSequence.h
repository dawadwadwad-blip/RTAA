#pragma once

#include <cstdint>

namespace RVA::Slice
{
enum class Job : std::uint8_t { NightShift, HillClimb, SurveyStakes, Complete };

class Sequence
{
public:
    constexpr Job Current() const { return Next; }

    constexpr bool Resolve(Job Completed)
    {
        if (Next != Completed || Next == Job::Complete)
        {
            return false;
        }
        Next = static_cast<Job>(static_cast<std::uint8_t>(Next) + 1);
        return true;
    }

private:
    Job Next = Job::NightShift;
};
}
