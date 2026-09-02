# Синтез для брейншторма: не «какую игру», а зачем она изменит поведение

- Статус: выводы исследования, не решение команды.
- Дата среза: 2026-09-02.
- Основание: [baseline X5](../x5-loyalty-current-state.md),
  [матрица кейсов](competitive-case-matrix.md) и
  [экспериментальные исследования](evidence-mechanisms.md).

## Ответ на исходный конфликт

Конфликт сформулирован верно:

> У X5 уже есть игры; поэтому добавление ещё одной игры, коллекции или аватара
> не является ни продуктовой новизной, ни причинной гипотезой эффекта.

Публичные данные X5 подтверждают большой игровой baseline — около 9 млн
участников в 2025 году — но не раскрывают incremental frequency или margin.
Конкуренты подтверждают ту же развилку:

- «Магнит» масштабирует сменяемые игры и заявляет +7,4% частоты против
  «схожих» неиграющих, но без дизайна matching и экономики;
- Пандагочи и «Бьюти-тамагочи» показывают массовый интерес к care/avatar-loop,
  но одновременно меняют задания, скидки, контент, коллекцию и новизну;
- Ozon получил хороший игровой engagement, однако отраслевой кейс сообщает об
  A/B-сигнале каннибализации покупок и рекламной выручки ранней версией;
- Tesco, Carrefour и ВкусБэк связывают прогресс непосредственно с историей
  покупок, но публично не отделяют framing от cash-like reward.

Следовательно, содержательная гипотеза должна звучать не «аватар повысит
лояльность», а, например:

```text
для сегмента S с поведенческим разрывом G
механизм M меняет медиатор P
и поэтому действие B происходит чаще относительно текущего опыта X5;
эффект остаётся после reward cost, cannibalization и fraud.
```

`M` может использовать avatar, progress, challenge или social element, но
элемент не заменяет механизм.

## Что считается фактом, выводом и гипотезой

### Факты из публичных источников

- X5, «Магнит», Самокат и «Золотое Яблоко» уже используют задачи, игровую
  валюту, progress, персонажей/коллекции и cash/chance rewards.
- У X5 уже есть персональные задания/рекомендации; у Tesco и Пандагочи цели и
  пороги зависят от покупательской истории или сегмента.
- Почти все крупные commercial cases публикуют охват и engagement, но не
  randomized incremental margin.
- Международные и российские механики закрывались или менялись по разным
  причинам; retirement сам по себе не доказывает отрицательный uplift.
- В контролируемых исследованиях разные элементы давали разные результаты:
  больше действий без intrinsic motivation, неоднородный эффект leaderboard,
  distraction, satiation и иногда crowding-out денежной наградой.

### Выводы из сопоставления

- Главный незакрытый вопрос X5 — не способность запустить игру, а способность
  выбрать для пользователя следующий **инкрементальный и достижимый** шаг,
  связать разрозненные кампании и доказать эффект поверх текущего опыта.
- Persistent layer может уменьшать фрагментацию, но одновременно создаёт
  обязательство поддерживать контент, экономику и сохранность прогресса.
- Самые легко измеримые механики превращают ценное действие в progress; самые
  визуально богатые часто хуже позволяют атрибутировать business effect.
- Поведенческая ЦА полезнее образа «геймера»: natural cadence, lifecycle state,
  headroom, promo sensitivity и digital readiness ближе к причинной цепочке,
  чем возраст или пол.

### Пока только гипотезы

- что единый meta-progress добавит эффект к уже существующим играм X5;
- что avatar создаст ownership, достаточный для дополнительной покупки;
- что personalized challenge будет лучше generic attainable challenge;
- что cohort rating мотивирует нижнюю часть распределения, а не только лидеров;
- что non-cash reward сохранит ценность в утилитарной grocery-категории;
- что referral привлечёт инкрементального клиента дешевле альтернативного CAC.

Эти пункты нельзя превращать в параметры симуляции без диапазона и маркировки
допущения.

## Повторяющиеся patterns успеха

Успех здесь означает правдоподобный механизм и/или измеренный outcome в своём
контексте, а не автоматическую рекомендацию для X5.

1. **Frequency fit.** Starbucks работает рядом с частым coffee ritual, Duolingo
   — с дешёвым daily lesson, grocery-challenges — с недельным/месячным циклом.
   Перенос механики без переноса cadence ломает смысл streak.
2. **Один ясный target.** ВкусБэк — разные SKU и оценки, Tesco — spend в
   выбранной категории, referral — первая квалифицирующая покупка. Это сильнее
   набора несвязанных кликов.
3. **Автоматический feedback.** Чек, заказ или урок обновляет progress без
   ручной регистрации. Walgreens показывает сильный early drop-off и разницу
   между automatic-device и manual users.
4. **Достижимые ступени.** Carrefour использует несколько порогов, endowed
   progress повышал completion при той же экономике, Duolingo добавляет grace.
5. **Choice без полной неопределённости.** Tesco предлагает набор целей,
   ВкусБэк — категории награды, Sephora — тематический маршрут. Пользователь
   сохраняет agency, система — budget/eligibility control.
6. **Utility вне скидки.** Nike даёт tracking/coaching, Sephora — discovery,
   «5 букв» — короткое mastery. Именно самостоятельная ценность позволяет
   возвращаться без новой денежной награды.
7. **Разделение валют.** Soft currency даёт частый feedback, cash-like reward
   можно выдавать реже и после economy/fraud gate.
8. **Обновляемый контент поверх стабильного контура.** Сезоны меняют тему, но
   сохраняют понятные progress, wallet или identity. Цена — content operations.
9. **Business guardrail внутри игровой оптимизации.** Ozon показывает, почему
   game retention нельзя улучшать без покупок, маржи и времени до целевого
   действия.

## Failure modes и отрицательные сигналы

| Failure mode | Что его иллюстрирует | Что проверять в X5 |
|---|---|---|
| Engagement без business effect | большинство PR-метрик; null effect на purchase intention в Bekk et al. | purchase frequency и margin/user, а не sessions |
| Каннибализация core journey | нераскрытый A/B-сигнал Ozon | catalog/promo conversion и time-to-purchase |
| Self-selection, названный uplift | игроки против неиграющих, VIP и challenge starters | random holdout или credible pre-period/matching |
| Reward объясняет весь эффект | Tesco, avatars и promo-games меняют всё сразу | reward-only и component arms |
| Несоответствие natural cadence | daily loops из learning/coffee в grocery | target относительно personal interpurchase interval |
| Satiation/novelty | повтор одной активности; сезонная ротация контента | несколько циклов и post-treatment window |
| Complexity и непрозрачность | упрощение и отмена tiers «СберСпасибо» | 1–2 условия, explanation и reachable tiers |
| Self-banishing comparison | heterogeneous leaderboard effect | effect по стартовой позиции, opt-out, private cohort |
| Proxy farming | XP grinding, manual health logs | valuable event, caps, anomaly/fraud reasons |
| Fraud вне customer score | insider diversion Monopoly prizes | separation of duties и audit trail наград |
| Persistent asset без continuity | Odyssey, FuelBand, «Плюс Сити» | recovery/end-of-life и ценность после сезона |
| Лишние sensitive data | health/location programs, global rating | pseudonymous ID и data minimization |

## Линза ЦА перед обсуждением механики

Команде не обязательно выбирать сегмент сейчас, но каждую идею стоит прогнать
через одинаковые вопросы.

| Признак | Почему меняет решение |
|---|---|
| Personal purchase cadence | определяет разумное окно и не позволяет навязать daily purchase |
| Lifecycle: new / stable / cooling / churned | разные цели: onboarding, breadth, timing или reactivation |
| Headroom | у power user может не быть безопасного запаса частоты |
| Promo sensitivity и organic baseline | показывает риск просто оплатить запланированную покупку |
| Breadth и category affinity | отделяет полезный discovery от нерелевантного cross-sell |
| Digital readiness | определяет friction, latency tolerance и доступность feedback |
| History depth | задаёт границу personalization и cold-start fallback |
| Motivation | savings, convenience, discovery, mastery, identity, social или chance требуют разных loops |
| Competition preference | публичное сравнение части пользователей помогает, части вредит |
| Household context | чек и referral могут отражать домохозяйство, а не одного человека |

Возраст/пол допустимы как moderators после проверки. Наблюдение «ядро игр
Магнита — женщины 35–44» полезно для опровержения стереотипа, но не является
правилом назначения игры всем женщинам 35–44.

## Отдельно об аватаре

### Когда у него есть работа

Аватар содержателен, если он:

- сохраняет один прогресс между временными кампаниями;
- делает вклад пользователя видимым и «своим»;
- немедленно отражает подтверждённые покупки/задачи;
- служит sink для дешёвой collection/customization currency;
- поддерживает opt-in cooperation или small-cohort identity;
- помогает понять следующий шаг, а не закрывает его анимацией.

### Когда это только оформление

- внешний вид меняется от уже существующего баланса, но поведение не меняется;
- customization не имеет связи с мотивацией сегмента;
- персонаж живёт в отдельном экране и конкурирует с покупкой;
- ежедневный decay создаёт guilt без natural daily action;
- вместе с ним одновременно добавлены скидка, challenge, push и новый UI;
- успех измеряется открытием экрана или временем с персонажем.

Минимально идентифицируемая проверка:

```text
A: одинаковые segment + challenge + reward + progress feedback
B: всё то же + persistent/customizable/reactive avatar
```

Если нужен эффект не avatar, а всего meta-layer, это следует так и назвать.

## Территории для брейншторма — не shortlist

Территории намеренно описаны как вопросы. Команда может отвергнуть их или
собрать другую связку.

1. **Gameful utility:** можно ли превратить чеки, экономию или категорийное
   discovery в полезный progress без отдельной мини-игры?
2. **Persistent identity:** есть ли у сегмента ценность, которую стоит сохранять
   между кампаниями, и является ли avatar лучшим carrier этой ценности?
3. **Personal next-best goal:** может ли система предложить не любимый товар,
   а достижимое изменение поведения с объяснением и organic baseline?
4. **Private social/cooperation:** может ли friend/referral/cohort loop дать
   accountability без ФИО, адреса и глобального top-N?
5. **Campaign container:** можно ли объединять уже существующие игры общими
   progress/wallet/rules, не строя ещё одну дорогую вселенную?

У каждой территории должен быть ответ на вопрос: почему текущие достижения и
игры X5 этого ещё не делают. Отсутствие публичного подтверждения функции X5
следует формулировать как вопрос кейсодателю, а не как факт отсутствия.

## Фильтр идеи перед shortlist

Идея допускается к обсуждению PoC, если команда может компактно заполнить все
строки:

| Поле | Обязательный ответ |
|---|---|
| Segment | кто имеет history, digital access и headroom |
| Gap | какое поведение относительно baseline нужно изменить |
| Existing X5 | чем это отличается от текущих игр/achievements/offers |
| Mechanism | какой mediator меняет поведение и почему у этой ЦА |
| Non-cash value | зачем вернуться без новой скидки; либо честно «нет» |
| Target event | одно автоматически проверяемое полезное действие |
| Economy | organic baseline, expected incremental margin, cost, funding, cap |
| Fraud/privacy | как фармят и какие минимальные данные нужны |
| Counterfactual | какая контрольная группа отделяет reward и game |
| Kill criterion | при каком результате идею прекращают/упрощают |
| PoC fit | как causal chain видна на 3–4 экранах и синтетических данных |

Красный флаг: ответ на Gap, Mechanism и Non-cash value повторяет название
элемента — «люди вернутся, потому что будет аватар/рейтинг/челлендж».

## Карта эксперимента

### Control

Контроль для реального X5 — текущий доступный loyalty/game experience, а не
«пустое приложение». Иначе тест измерит всю программу против отсутствия
программы, а не добавочную ценность нового слоя.

### Возможные arms

Их набор — командное решение и зависит от трафика:

1. current experience / no new offer;
2. same target + cash-like reward, neutral presentation;
3. same target + reward + progress/game framing;
4. same target + reward + progress + tested component: avatar/rating/social;
5. generic attainable target против personalized target.

Главное — менять по одному причинному компоненту или честно называть treatment
пакетом.

### Outcomes и guardrails

- primary: доля с ≥N qualifying purchases или frequency uplift;
- economics: incremental contribution margin per eligible user после expected
  redemption, funding и variable cost;
- diagnostics: offer/activation/progress/completion/claim funnel;
- heterogeneity: baseline frequency, lifecycle, starting rank, digital/history;
- harm: opt-out, complaints, lower retention, food-waste proxy при наличии;
- fraud: suspicious receipt/referral rate, reward hold, false positives;
- durability: treatment, несколько natural cycles и post-treatment.

### Что делать с симуляцией

Не подставлять внешние +7,4%, +14% или ROI 127% как «ожидаемый uplift X5».
Использовать диапазоны и sensitivity analysis:

```text
expected_net_effect
  = eligible_users
  × incremental_action_probability
  × margin_per_incremental_action
  - expected_reward_cost
  - variable_service_and_fraud_cost
```

Симуляция проверит, при каких предположениях экономика сходится, но причинный
`incremental_action_probability` должен дать пилот.

## Короткий canvas для командного брейншторма

Для каждой идеи достаточно одной строки на пункт:

1. сегмент и его baseline;
2. незакрытый job/behavioral gap;
3. одно qualifying action;
4. причинный механизм;
5. роль каждого игрового элемента;
6. причина вернуться без новой скидки;
7. награда, cap и кто платит;
8. способ фарма и reward-hold;
9. control/arms и primary metric;
10. kill criterion.

После заполнения идеи можно сравнить по [12 осям из плана](research-plan.md), не
назначая веса до командного выбора сегмента и продуктовой цели.
