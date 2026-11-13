# Decisions & thresholds

Every threshold or rule we had to choose, and why. (Required in the README hand-in.)

| # | Decision | Why |
|---|---|---|
| 1 | Money is `Decimal`, rounded half-up to paise | Spec compares within ₹1; float drift can flip a match |
| 2 | *Missing* tasks filter Meridian records by **delivery** month; all other tasks by **invoice-date** month | Stated in the brief; 8 public shipments cross a month boundary |
| 3 | Team key, passwords and the tasks URL live only in `.env` | Brief forbids them in prompts, traces, screenshots and commits |
