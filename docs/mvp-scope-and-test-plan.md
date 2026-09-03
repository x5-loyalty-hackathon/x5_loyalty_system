# Обязательный MVP, Day 1 и test gates

- **Статус:** командный current state, 2026-09-03.
- **Промежуточная сдача:** 04.09.2026 10:00.
- **Финальная сдача:** 07.09.2026 10:00.
- **Роли:** ML/Recsys & Evaluation; Product/UX & Frontend;
  Backend/Integration/Safety.

## 1. Зафиксированное продуктовое ядро

Обязательно для общей версии решения:

```text
чек
→ персональные current/repeat/explore рецепты
→ ingredients: bought/home/markdown/full-price/unavailable
→ доставка или следующий визит
→ новый чек
→ прогресс Домового и личная статистика
```

- ЦА: домохозяйства, покупающие продукты для приготовления блюд.
- Рецепты проходят relevance/safety threshold; затем меньше missing items выше.
- Новый рецепт может содержать продукты без точного аналога в истории.
- Markdown выбирается только внутри ингредиентов рецепта.
- Out-of-recipe cross-sell отсутствует.
- Радиус вместо одного домашнего магазина.
- Отдельной брони rescue SKU нет.
- Нет дополнительной денежной награды.
- Gambling-like слой и public leaderboard исключены.
- Recipe feed доступен ежедневно; push не ежедневный.
- Личная статистика: рецепты, фактическая экономия, rescue items и развитие дома.

Не зафиксированы командой и остаются demo-настройками: `10 XP` за новый день
покупки, `20 XP` за завершённый рецепт, `10 XP` за referral и `50 XP` на
уровень. Их можно менять после продуктового согласования, не меняя API flow.

## 2. Definition of Day 1

Day 1 не обязан быть финальным продуктом. К промежуточной сдаче обязательно:

| Контур | Минимальный результат | Evidence |
|---|---|---|
| Product | ЦА, гипотеза, value proposition, 4-screen flow, риски | compact product artifact |
| UX | кликабельный happy path на mock data | ссылка/скриншоты |
| ML/Recsys | синтетические профили, стабильный output contract, первые recommendations | ≥5 примеров, preliminary eval |
| Backend | API schemas, mock engine, safety wrapper | runnable service и API example |
| Safety | expired/unsafe/excluded/radius/fallback rules | automated tests |
| Submission | slides, Markdown description, product materials, repo link | загруженные intermediate artifacts |

Можно честно оставить `planned after Day 1`:

- model adapter вместо mock;
- persistent adapter вместо process-local demo state;
- расширение basic referral/antifraud после review;
- evaluation на полных 30–50 профилях;
- simulation 1–10k;
- polished visual states и final deployment.

## 3. Обязательная финальная реализация

| Требование кейса | Реализация | Owner | Automated/evidence gate |
|---|---|---|---|
| 3–4 связанных экрана | after-receipt → recipe → plan → personal kitchen | Product/UX | happy-path UI smoke |
| Персональный AI challenge | model ranks recipe/mode from synthetic history | ML/Recsys | relevance ≥70% |
| Выбор механики с объяснением | `current/repeat/explore` + reason codes | ML + Backend | schema + own/shuffled eval |
| Прогресс аватара | verified receipt updates bounded XP/level | Backend | idempotency tests |
| Место в рейтинге | private position/percentile without public identities | Backend | rank tests, no leaderboard endpoint |
| Referral reward | virtual progress, monetary value `0`, one reward/invitee | Backend | qualification/idempotency/fraud tests |
| Антифрод чеков | duplicate owner, cross-user replay, future event, same-day collapse | Backend/Safety | threshold and state tests |
| Антифрод referrals | self/duplicate attribution, device/payment collision | Backend/Safety | precision-first tests |
| Simulation 1–10k | profiles × receipts × recipes × availability | ML/Recsys | deterministic seed + sanity checks |
| Экономика | purchase-day, whole-basket и rescue value не смешиваются | ML/Product | invariant/sensitivity checks |
| Pilot plan | 30/60-day control design and guardrails | Product + review | one-page checklist |

## 4. Backend increments

### B1 — завершено

- recommendation contract v1;
- mock/model protocol;
- post-model safety;
- markdown/full-price fallback;
- delivery/next_visit response;
- example JSON и API tests.

### B2 — реализован в рабочей ветке, ожидает review

- receipt event contract;
- idempotent in-memory state;
- unique purchase-day aggregation;
- recipe progress, savings и rescue count;
- private rank/percentile;
- explainable receipt fraud status.

### B3 — реализован в рабочей ветке, ожидает review

- referral qualification;
- one invitee → one inviter;
- virtual-progress reward calculation;
- self/device/payment collision policy;
- pending/review vs hard reject.

Текущие fraud weights и thresholds — объяснимые demo-константы, а не
измеренные production-пороги. Перед пилотом их нужно подобрать на размеченной
выборке; до этого precision-first достигается тем, что неоднозначные совпадения
device/payment направляются в review, а не блокируются автоматически.

### B4

- model adapter integration;
- frontend integration smoke;
- deterministic demo scenario;
- exportable OpenAPI/example responses;
- final operational/error states.

### Межкомандные integration gates

1. ML owner прогоняет свой adapter по тем же Pydantic schemas; contract tests
   остаются зелёными.
2. Frontend owner воспроизводит happy path сначала на example response, затем
   на живом API без изменения экранного сценария.
3. Backend owner поддерживает end-to-end fixture: recommendation → receipt →
   progress → qualified referral.
4. Команда вместе принимает только продуктовые константы, primary metric и
   экономические assumptions; технический owner не фиксирует их единолично.

## 5. Test pyramid

```text
few UI / end-to-end smoke tests
      API integration tests
    service and state tests
 schema / policy unit tests
```

### Blocking on every backend change

- GitHub Actions проходит на Python 3.11 и 3.14;
- all tests pass;
- contract schema remains backward-compatible inside v1;
- unknown input fields fail explicitly;
- duplicate event, в том числе конкурентный, never changes state twice;
- hard safety rule cannot be bypassed by model score;
- no endpoint exposes names/addresses or a public leaderboard;
- no simulated result is labelled as causal evidence.

### Required test groups

| Group | Checks |
|---|---|
| Contract | validation, enums, version, forbidden extra fields |
| Recommendation | modes, missing sort, reason codes, model adapter boundary |
| Safety | expired, unsafe, exclusions, radius, verified recipe |
| Availability | markdown → full-price → unavailable, delivery/visit |
| Receipt state | duplicate, cross-user replay, same-day collapse, future time |
| Progress | bounded update, savings, rescue count, avatar level, private rank |
| Referral | qualification, one-time reward, self/collision handling |
| Integration | example scenario from request to personal progress |

## 6. Optional only after mandatory

- gambling-like `забрать / рискнуть`;
- public/social leaderboard;
- real-time reservation;
- physical pre-built rescue boxes;
- LLM recipe generation;
- production delivery/catalog integration;
- admin UI and complex fraud model;
- extra cross-sell outside selected recipe.

Optional work cannot delay a mandatory test gate or final artifact.
