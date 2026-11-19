#include "ChurchHillJobProgress.h"

#include <cstdlib>
#include <cstdio>
#include <limits>

using namespace RVA::ChurchHill;

#define REQUIRE(Condition) \
    do { \
        if (!(Condition)) { \
            std::fprintf(stderr, "failed at line %d: %s\n", __LINE__, #Condition); \
            return EXIT_FAILURE; \
        } \
    } while (false)

int main()
{
    HillClimbProgress Hill;
    REQUIRE(!Hill.Choose(HillRoute::Direct));
    REQUIRE(Hill.Load() && !Hill.Load() && !Hill.Choose(HillRoute::Unset));
    REQUIRE(Hill.Choose(HillRoute::Direct) && !Hill.Choose(HillRoute::Gentle));
    REQUIRE(!Hill.Deliver(0.0) && !Hill.RecordDrive(0.04, 17, 0.1) && Hill.GetSlip() == 0.0);
    REQUIRE(!Hill.RecordDrive(1.0, std::numeric_limits<double>::quiet_NaN(), 0.1));
    REQUIRE(!Hill.RecordDrive(0.19, 20, 0.25) && Hill.GetSlip() > 0.0);
    REQUIRE(!Hill.RecordDrive(0.19, 20, 0.25));
    REQUIRE(Hill.RecordDrive(0.19, 20, 0.25) && Hill.GetPhase() == HillPhase::StopToSecure);
    REQUIRE(!Hill.Deliver(0.0) && !Hill.Secure(1.0));
    // Cargo slips before the warning. Passing it still counts toward delivery.
    REQUIRE(Hill.ReachWarning() && !Hill.ReachWarning() && Hill.GetPhase() == HillPhase::StopToSecure);
    REQUIRE(Hill.Secure(0.3) && Hill.GetSlip() == 0.0 && !Hill.ReachWarning());
    REQUIRE(!Hill.Deliver(3.0) && Hill.Deliver(0.2) && !Hill.Deliver(0.2) && !Hill.ResetIfCargoLost());

    HillClimbProgress Lost;
    REQUIRE(Lost.Load() && Lost.Choose(HillRoute::Gentle) && Lost.ResetIfCargoLost());
    REQUIRE(Lost.GetPhase() == HillPhase::AwaitingLoad && Lost.GetRoute() == HillRoute::Unset);
    REQUIRE(Lost.Load() && Lost.Choose(HillRoute::Gentle) && Lost.ReachWarning() && Lost.Secure(0.0));
    REQUIRE(Lost.Deliver(0.0) && Lost.GetRoute() == HillRoute::Gentle);

    SurveyStakesProgress Survey;
    REQUIRE(!Survey.MarkSite(0) && !Survey.Begin(SurveyMethod::Hard, 0.0));
    REQUIRE(Survey.Begin(SurveyMethod::Hard, 10.0) && !Survey.Begin(SurveyMethod::Kind, 0.0));
    REQUIRE(Survey.MarkSite(0) && !Survey.MarkSite(0) && !Survey.MarkSite(2));
    REQUIRE(!Survey.Tick(3.0) && Survey.GetSecondsLeft() == 7.0 && Survey.Tick(7.0));
    REQUIRE(Survey.GetPhase() == SurveyPhase::Available && !Survey.HasSite(0));
    REQUIRE(Survey.Begin(SurveyMethod::Hard, 10.0) && Survey.MarkSite(1) && Survey.MarkSite(0));
    REQUIRE(Survey.GetPhase() == SurveyPhase::Complete && !Survey.MarkSite(1) && !Survey.Tick(30.0));

    SurveyStakesProgress Kind;
    REQUIRE(Kind.Begin(SurveyMethod::Kind, 0.0) && !Kind.Tick(1000.0));
    REQUIRE(Kind.MarkSite(0) && Kind.MarkSite(1) && Kind.GetMethod() == SurveyMethod::Kind);

    std::puts("PASS: Hill Climb routes and cargo recovery, Survey Stakes methods and timeout");
    return EXIT_SUCCESS;
}
