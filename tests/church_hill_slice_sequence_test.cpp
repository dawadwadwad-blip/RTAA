#include "ChurchHillSliceSequence.h"

#include <cassert>
#include <iostream>

int main()
{
    using RVA::Slice::Job;
    using RVA::Slice::Sequence;

    Sequence Slice;
    assert(Slice.Current() == Job::NightShift);
    assert(!Slice.Resolve(Job::HillClimb));
    assert(!Slice.Resolve(Job::SurveyStakes));
    assert(Slice.Resolve(Job::NightShift));
    assert(Slice.Current() == Job::HillClimb);
    assert(!Slice.Resolve(Job::NightShift));
    assert(!Slice.Resolve(Job::SurveyStakes));
    assert(Slice.Resolve(Job::HillClimb));
    assert(Slice.Current() == Job::SurveyStakes);
    assert(!Slice.Resolve(Job::HillClimb));
    assert(Slice.Resolve(Job::SurveyStakes));
    assert(Slice.Current() == Job::Complete);
    assert(!Slice.Resolve(Job::SurveyStakes));
    assert(!Slice.Resolve(Job::Complete));
    assert(Slice.Current() == Job::Complete);
    std::cout << "PASS: Church Hill slice advances each mission once in playtest order\n";
}
