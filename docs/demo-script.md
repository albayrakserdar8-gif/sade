# Demo video script (about 4 minutes)

Each scene: what is on screen, the Otari feature it shows, and the narration.
The narration below is the exact text of the voice-over.

| # | Screen | Otari feature |
|---|---|---|
| 1 | Title card | — |
| 2 | Photo of the sample enforcement order | — (the problem) |
| 3 | App home, user Ayşe selected | per-user budgets (setup) |
| 4 | Result card for the enforcement order | open-weight models |
| 5 | "Text sent to the model", masked | privacy |
| 6 | Otari panel: calls table | distinct roles, routing |
| 7 | Otari panel: sandbox code and output | code execution |
| 8 | Otari panel: web searches, guardrails, MCP calls | web search, guardrails, MCP |
| 9 | Draft petition | open-weight models |
| 10 | Otari panel after "simulate a provider outage" (photo reading falls back) | routing & fallbacks |
| 11 | Hidden-injection tax letter, blocked | guardrails |
| 12 | Masking turned off, blocked | guardrails |
| 13 | Mehmet over budget, blocked | per-user budgets |
| 14 | Otari dashboard: Spend & budgets | budgets & spending limits |
| 15 | Otari dashboard: Routing policies | routing & fallbacks |
| 16 | Otari dashboard: Sessions | observability |
| 17 | Closing card with the feature list | all |

## Narration

**1.** This is Sade, a plain-language assistant for Turkish official letters. Every AI call goes through Otari, and every model is open-weight.

**2.** In Turkey, tax notices, enforcement orders and landlord notices are written in dense legal language, and their deadlines are short. You have seven days to object to an enforcement order. Miss it, and the debt becomes final. These letters are also full of personal data.

**3.** Here is the app. Each user has their own Otari API key, with its own budget. Ayşe uploads a phone photo of an enforcement order.

**4.** In about half a minute, Sade explains what the letter is, who sent it, and what to do. Object within seven days, by Tuesday the third of November. Pay within ten days, by Friday the sixth. Each deadline has an add-to-calendar button.

**5.** Before any text reaches a model, Sade replaces the national ID number, the name and the address with placeholders. The real values are filled back in only on the user's side.

**6.** The Otari panel shows what happened. Four open-weight models, each in its own role. DeepSeek V4.1 Flash read the photo, through the routing policy sade-ocr. Ministral 3 8B classified the document. DeepSeek analysed it, through the policy sade-analyst. And gpt-oss-safeguard judged the letter for prompt injection.

**7.** Deadlines are never computed in the model's head. The analyst writes Python, and Otari runs it in its own sandbox. Here is the code, and its output.

**8.** The analyst also used Otari's web search to confirm the law articles on official sites. Otari ran two guardrails from our own service before any model saw the text, and both passed. And the model called our own MCP server, sade-takvim, for public holidays, a working-day check, and a calendar event for each deadline.

**9.** When a reply is needed, one click drafts the objection petition in formal Turkish, with the user's details filled in locally.

**10.** Now, routing and fallbacks. With "simulate a provider outage" turned on, reading the photo goes to a policy whose first provider has a broken key. Otari falls back on its own: second attempt, same model on DeepInfra. The user never notices.

**11.** Guardrails. This tax letter hides a tiny, pale line telling the AI to say the debt is invalid. Otari sends the text to our guardrail service, the open-weight judge flags it, and Otari blocks the request with a 403. No model ever sees the letter.

**12.** And if masking is turned off, the personal-data guardrail stops the request as well.

**13.** Budgets. Mehmet is on a trial plan of five cents a day, and he has used it up. Otari refuses his next request before any model runs, and the app tells him his limit is reached.

**14.** In the Otari dashboard, there is a monthly ceiling for the whole organization, and a budget on each user's key.

**15.** These are the routing policies the app calls by name.

**16.** And every analysis appears as one session on the Otari dashboard, with its calls, tokens and cost.

**17.** Open-weight models in distinct roles, routing and fallbacks, code execution, web search, MCP, guardrails, budgets, and per-user budgets. All through Otari. The code is on GitHub, at sadopc slash sade. Thanks for watching.
