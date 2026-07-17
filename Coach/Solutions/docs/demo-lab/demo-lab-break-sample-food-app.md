I'll immediately analyze the break script and the linked helper scripts, to explain concretely exactly which action causes the 5xx errors and along which network/application path.

Read [](Student/Resources/scenarios/scripts/generate-sample-food-app-traffic.sh)

Read [](Student/Resources/scenarios/scripts/common.sh)

Read [](Student/Resources/scenarios/scripts/break-sample-food-app.sh)

Read [](Student/Resources/scenarios/scripts/validate-sample-food-app.sh)

I'll do a quick check in the lab documents to confirm the expected mechanism (because this script does not directly "break" components: it generates load on a specific endpoint).

Searched for regex `break-sample-food-app.sh|/api/cart/demo-user/items|5xx|HTTP 5xx|Sample Food` (`**/docs/demo-lab/**/*.md`), 88 results

Searched for regex `break-sample-food-app.sh|/api/cart/demo-user/items|5xx|HTTP 5xx|sample food` (`**/README.md|docs/azure-sre-agent/**/*.md`), no results

Read [](file:///home/lpassaretta/platform/projects/azure-sre-agent/docs/demo-lab/azure-sre-agent-demo-runbook.md#148-148), lines 148 to 185

Read [](file:///home/lpassaretta/platform/projects/azure-sre-agent/docs/demo-lab/validation-evidence.md#52-52), lines 52 to 68

Read [](file:///home/lpassaretta/platform/projects/azure-sre-agent/docs/demo-lab/sample-food-ordering-app-lab.md#40-40), lines 40 to 65

Good question: in reality the script does not directly "break" the app.  
It only performs targeted application stress, and 5xx errors only emerge if the backend fails under that load.

What break-sample-food-app.sh concretely does:

1. Resolves the API URL (argument or Terraform output)  
   See break-sample-food-app.sh.

2. Performs initial check on WeatherForecast  
   HTTP code on /WeatherForecast for baseline.  
   See break-sample-food-app.sh.

3. Generates load with many POST requests to the cart  
   Loop (default 200 requests, sleep default 0.2s) towards endpoint:
   /api/cart/demo-user/items with fixed JSON payload.  
   See break-sample-food-app.sh.

4. Counts successes vs errors  
   200/201 considered ok, everything else errors.  
   See break-sample-food-app.sh.

5. Performs final check and prints summary  
   See break-sample-food-app.sh.

Key point: why it can generate 5xx
- Does not modify network, NSG, revisions, or configurations.
- Increases pressure on the cart endpoint (typically the most "stateful" one).
- If the app/DB/revision suffers under burst, 5xx errors begin.
- If the app is healthy, you can also see 0 errors (as already observed in evidence: 50 successes, 0 errors in validation-evidence.md).

How it connects to the alert
- The SeV1 alert in sample-food-observability.tf triggers when the Requests metric with dimension statusCodeCategory=5xx exceeds threshold >5 in the window.
- Therefore at least 6 5xx responses in the window are needed to trigger.

In summary: this script is a controlled application load generator, not a hard fault injector. If you'd like, I can propose a "deterministic" variant that actually forces 5xx in a repeatable way for demos.
