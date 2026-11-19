#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace RVA::ChurchHill
{
enum class HillRoute : std::uint8_t { Unset, Gentle, Direct };
enum class HillPhase : std::uint8_t { AwaitingLoad, ChooseRoute, Hauling, StopToSecure, Delivered };

class HillClimbProgress
{
public:
    HillPhase GetPhase() const { return Phase; }
    HillRoute GetRoute() const { return Route; }
    double GetSlip() const { return Slip; }

    bool Load() { return Advance(HillPhase::AwaitingLoad, HillPhase::ChooseRoute); }

    bool Choose(HillRoute Choice)
    {
        if ((Choice != HillRoute::Gentle && Choice != HillRoute::Direct)
            || !Advance(HillPhase::ChooseRoute, HillPhase::Hauling))
        {
            return false;
        }
        Route = Choice;
        return true;
    }

    bool ReachWarning()
    {
        if (bFinalWarning || Phase != HillPhase::Hauling)
        {
            return false;
        }
        bFinalWarning = true;
        Phase = HillPhase::StopToSecure;
        return true;
    }

    bool RecordDrive(double Grade, double MetresPerSecond, double Seconds)
    {
        if (Phase != HillPhase::Hauling || !std::isfinite(Grade) || !std::isfinite(MetresPerSecond)
            || !std::isfinite(Seconds) || Seconds <= 0.0)
        {
            return false;
        }
        const double ExcessGrade = std::max(0.0, std::clamp(std::abs(Grade), 0.0, 1.0) - 0.065);
        const double Speed = std::clamp(MetresPerSecond, 0.0, 26.0);
        Slip = std::clamp(Slip + ExcessGrade * Speed * 0.72 * std::min(Seconds, 0.25), 0.0, 1.0);
        if (Slip < 1.0)
        {
            return false;
        }
        Phase = HillPhase::StopToSecure;
        return true;
    }

    bool Secure(double MetresPerSecond)
    {
        if (!IsStopped(MetresPerSecond) || !Advance(HillPhase::StopToSecure, HillPhase::Hauling))
        {
            return false;
        }
        Slip = 0.0;
        return true;
    }

    bool Deliver(double MetresPerSecond)
    {
        return bFinalWarning && IsStopped(MetresPerSecond) && Advance(HillPhase::Hauling, HillPhase::Delivered);
    }

    bool ResetIfCargoLost()
    {
        if (Phase == HillPhase::AwaitingLoad || Phase == HillPhase::Delivered)
        {
            return false;
        }
        *this = HillClimbProgress();
        return true;
    }

private:
    HillPhase Phase = HillPhase::AwaitingLoad;
    HillRoute Route = HillRoute::Unset;
    double Slip = 0.0;
    bool bFinalWarning = false;

    bool Advance(HillPhase Before, HillPhase After)
    {
        if (Phase != Before)
        {
            return false;
        }
        Phase = After;
        return true;
    }

    static bool IsStopped(double MetresPerSecond) { return MetresPerSecond >= 0.0 && MetresPerSecond <= 0.8; }
};

enum class SurveyMethod : std::uint8_t { None, Kind, Hard };
enum class SurveyPhase : std::uint8_t { Available, Working, Complete };

class SurveyStakesProgress
{
public:
    SurveyPhase GetPhase() const { return Phase; }
    SurveyMethod GetMethod() const { return Method; }
    double GetSecondsLeft() const { return SecondsLeft; }

    bool Begin(SurveyMethod NewMethod, double TimeLimit)
    {
        if (Phase != SurveyPhase::Available || (NewMethod != SurveyMethod::Kind && NewMethod != SurveyMethod::Hard)
            || (NewMethod == SurveyMethod::Hard && (!std::isfinite(TimeLimit) || TimeLimit <= 0.0)))
        {
            return false;
        }
        Phase = SurveyPhase::Working;
        Method = NewMethod;
        SecondsLeft = Method == SurveyMethod::Hard ? TimeLimit : 0.0;
        return true;
    }

    bool HasSite(std::uint8_t Site) const
    {
        return Site < 2 && (Mask & (1u << Site)) != 0;
    }

    bool MarkSite(std::uint8_t Site)
    {
        if (Phase != SurveyPhase::Working || Site >= 2 || HasSite(Site))
        {
            return false;
        }
        Mask |= static_cast<std::uint8_t>(1u << Site);
        if (Mask == 3)
        {
            Phase = SurveyPhase::Complete;
        }
        return true;
    }

    bool Tick(double Seconds)
    {
        if (Phase != SurveyPhase::Working || Method != SurveyMethod::Hard || !std::isfinite(Seconds) || Seconds <= 0.0)
        {
            return false;
        }
        SecondsLeft = std::max(0.0, SecondsLeft - Seconds);
        if (SecondsLeft > 0.0)
        {
            return false;
        }
        *this = SurveyStakesProgress();
        return true;
    }

private:
    SurveyPhase Phase = SurveyPhase::Available;
    SurveyMethod Method = SurveyMethod::None;
    std::uint8_t Mask = 0;
    double SecondsLeft = 0.0;
};
}
