# Сравнительная матрица кейсов

- Статус: агрегация для брейншторма, не рейтинг и не shortlist.
- Дата среза: 2026-09-02.
- Подробности и источники: [X5 baseline](../x5-loyalty-current-state.md),
  [российский grocery](russia-grocery.md),
  [Россия вне grocery](russia-cross-industry.md),
  [международные кейсы](international-cases.md),
  [экспериментальные исследования](evidence-mechanisms.md).

## Как читать evidence

- **E1** — randomized/сильный causal design с нужным outcome;
- **E2** — сравнение или динамика, но остаётся selection/confounding;
- **E3** — корпоративный aggregate без контроля;
- **E4** — подтверждены механика/статус, но не эффект;
- `*` — дизайн заявлен компанией/вторичным кейсом, но необходимые детали не
  опубликованы.

Один кейс может иметь разные уровни: например, E3 для охвата и E4 для влияния
на покупки. Колонка показывает сильнейший релевантный публичный сигнал, а не
«оценку качества бренда».

## Baseline, с которым конкурирует будущая идея

| Система | Аудитория и cadence | Поведенческая задача | Loop и награда | Публичный сигнал | Диагноз для X5 |
|---|---|---|---|---|---|
| X5: текущие игры и достижения | Массовый grocery; покупки и app-контакты уже частые | Покупка, товарные задания, app engagement | Задание/чек → попытка/монеты/прогресс → баллы, купон или шанс | 9 млн участников игр в 2025, 22 сессии в месяц; **E3** | Новая идея должна превзойти не «отсутствие игры», а этот опыт по incremental frequency/margin |

## Россия: grocery и delivery

| Кейс | Аудитория и cadence | Поведенческая задача | Loop и награда | Публичный сигнал | Диагноз для X5 |
|---|---|---|---|---|---|
| «Магнит»: сменяемые игры | Ядро игроков — женщины 35–44; grocery cadence | Частота, товар партнёра, digital actions | Free play + задания/чек → кристаллы → купон/шанс/кастомизация | +7,4% частоты у «схожих» неиграющих; **E2***; охват 10,4 млн — **E3** | Прямой конкурентный baseline; matching и margin не раскрыты, ещё одна casual-game не дифференцирует |
| «Лентомания» | Держатели Карты № 1; крупная плановая корзина | Дневной вход, spend threshold, SKU/СБП | Три-в-ряд → билет/купон → розыгрыш | Результатов нет; **E4** | Seasonal promo-loop не создаёт persistent layer; есть риск недостижимого общего порога |
| «ВкусВилл»: ВкусБэк | Assortment explorers с готовностью оценивать товары | Basket breadth, feedback, возврат в следующем месяце | Разные SKU + оценки → tier → выбор cashback-категорий | Результатов нет; **E4** | Важный gameful-utility pattern: покупательская история сама является игровым полем |
| «ВкусВилл»: «Чистый состав» | Online/Telegram users; профиль не раскрыт | Product education и заказ от 2 000 ₽ | Fruit-ninja → промокод → заказ | Self-reported ROMI 180%, +1 178 ₽ к чеку; **E3** | Связь игры с product promise сильнее декора, но вклад промокода не отделён |
| Самокат: Пандагочи | Сегменты по baseline orders/AOV; q-commerce cadence | App return и персональные transaction tasks | Care/avatar → задание/заказ → рост, предметы и скидка | 1 млн+ users, 70% сделали задачу; рост заказов без размера; **E3** | Прямой avatar-аналог; эффект всего пакета не идентифицирует avatar |
| Самокат: Гастротур | 16–24; короткие q-commerce cycles | Asian-range orders, frequency, ARPPU | 40 уровней/сюжет → transaction task → offer/prize | ROI 127%, ARPPU +14%, частота ЦА +8,8% к среднему периода; **E3** | Хорошая target specificity, но self-selection и сравнение со средним не дают uplift |

## Россия: beauty, ecosystem, finance и marketplace

| Кейс | Аудитория и cadence | Поведенческая задача | Loop и награда | Публичный сигнал | Диагноз для X5 |
|---|---|---|---|---|---|
| «Золотое Яблоко»: тамагочи + Лаймовый клуб | App-аудитория преимущественно женщины 18–44; beauty-покупки реже grocery | Возврат, brand discovery, identity и онлайн-покупка | Care + avatar + collection + friends + season → soft/cash-like reward | 1,6 млн в первом сезоне, 7 млн за сезоны; business KPI закрыты; **E3** | Публично измерен весь beauty-fit loop, а не «эльф» отдельно; purchase/margin и avatar-only effect неизвестны |
| Яндекс «Плюс Сити» | Digital-ready подписчики мультисервисной экосистемы | Cross-service breadth и возврат | Использование сервиса → здание/ресурс → личный город/collection | 5 млн downloads и много игровых объектов; закрыт 20.03.2026; **E3/E4** | Persistent world требует continuity и content economics; закрытие не равно доказанному провалу |
| Т-Банк «5 букв» | Широкая по полу/возрасту аудитория; ежедневный app contact | Daily app visit и переход к partner offer | Короткое слово дня → feedback/streak → скидка/кешбэк | 7 млн игроков, 131 млн партий; **E3** | Полезный простой control для сложного meta-layer; business outcome не раскрыт |
| «СберСпасибо»: игры и бывшие tiers | Массовая банковская аудитория; частые card events | Card/service activity, partner traffic, cross-sell | Задания/операции → уровень/ход → категория/баллы/приз | +39% engagement до/после; tiers упрощены и отменены; **E2*** | Complexity, negative-economics segments и cheating способны разрушить средний эффект |
| Ozon «Морковск» | Массовый marketplace app; игра конкурирует с каталогом | App actions, seller traffic, покупки | Действие → морковки → игра/шанс → prize | Вторичный кейс сообщает A/B-каннибализацию purchase/ad revenue; **E2*** | Game retention должен иметь guardrails основного продукта и opportunity cost |
| Т-Банк «Приведи друга» | Клиент + новый для продукта знакомый | Acquisition и первое ценное действие | Link → approval → product → qualifying action → delayed bilateral reward | Правила зрелые, outcomes не раскрыты; **E4** | Переносим qualification lifecycle, а не банковский KYC или игровую оболочку |

## Международные кейсы

| Кейс | Аудитория и cadence | Поведенческая задача | Loop и награда | Публичный сигнал | Диагноз для X5 |
|---|---|---|---|---|---|
| Starbucks Rewards challenges | Frequent coffee/app users | Дополнительный визит, daypart/category trial | Personal mission → order → Stars → следующая покупка | 34,6 млн 90-day active и ~60% tender программы; challenge uplift неизвестен; **E3** | Малый friction и frequency fit важнее игры; нужен challenge-level holdout |
| Starbucks Odyssey | Узкий waitlist digital-superfans | Education, collection, access/community | Journey → NFT stamp/points → level/access/trade | Closed beta, закрыта 31.03.2024; KPI не раскрыты; **E4** | Tradable scarcity и отдельный web3 flow не создали доказанной mass utility |
| Sephora Beauty Insider Challenges | Beauty customers; discovery важнее daily purchase | Category exploration, quiz/data, digital actions | Join → mixed tasks → points/sample/experience | ~20% active clients попробовали challenge; **E3** | Non-purchase steps могут создавать utility/данные; VIP cohort имеет малый headroom |
| Tesco Clubcard Challenges | Grocery households с историей | Incremental category spend и app use | Выбор до 10 персональных целей → auto-progress → tiered points | 10 млн reach; 62% players получили первую награду; **E3** | Самый близкий AI-challenge pattern, но game framing не отделён от крупной награды |
| Carrefour Challenges / Bonusland | Bonus Card grocery users | Category/brand spend, visits, digitalization | Выбор brand/category → три порога → points/coupon | Vendor: +10–12% spend, +1 visit/month, ROI 7; **E3** | Tiered goals и campaign container переносимы; vendor ROI не causal evidence |
| McDonald's Monopoly | Массовая fast-food/app аудитория; campaign cadence | App acquisition и повтор в период акции | Qualifying item → rare piece/collection → claim/prize | Почти 500 млн plays в США в 2025; sales effect не выделен; **E3** | Chance даёт reach, не loyalty proof; insider prize fraud расширяет antifraud perimeter |
| Nike FuelBand → Run Club | Люди с intrinsic goal бега; daily/weekly practice | Exercise/mastery и brand contact | Track run → feedback/goal/friends → следующий run | Hardware/sync закрыты, software-loop жив; causal KPI нет; **E4** | Utility переживает оболочку; grocery purchase сам по себе не intrinsic activity |
| Duolingo streaks | Learners; действие дешёвое и естественно ежедневное | Regular practice/retention | Lesson → streak/XP/commitment/friend → завтра | Internal randomized A/B: до +14% D7 для wager, +4% week return для amulet; **E1*** | Переносим commitment/grace и guardrail, не daily purchase cadence |
| Walgreens Healthy Choices | Health/pharmacy users, разная digital readiness | Self-tracking и health actions | Goal/device/log → points → Walgreens discount | 455 341 users: 34% ушли после одного log; device users дольше; **E2** association | Автоматическое событие лучше ручного proxy; health data и easy farming не нужны X5 |

## Исследования, меняющие интерпретацию кейсов

| Результат | Evidence | Что он запрещает заключать |
|---|---|---|
| В mall field RCT badges и leaderboard увеличили продажи на 21,5% и 22,5%, но leaderboard дал self-reinforcing и self-banishing effects | E1 | Что ranking одинаково полезен всем и средний эффект безопасен |
| В supermarket experiment геймификация без фактического engagement могла снизить склонность использовать offer | E1 | Что наличие игры автоматически помогает shopping task |
| Points/levels/leaderboard увеличили количество действий, но не intrinsic motivation или качество | E1, lab | Что больше действий означает более ценное действие или устойчивую мотивацию |
| Avatar/story/teammates влияли на relatedness, другие элементы — на competence/meaningfulness | E1, lab | Что любой элемент взаимозаменяем и avatar сам ведёт к покупке |
| Monetary incentive устранял положительный attitudinal effect shopping-game в двух lab experiments | E1, lab | Что game effect и reward effect всегда складываются |
| Повтор одинаковой gamified activity давал satiation; meaningful integration снижала distraction harm | E1/E2, mainly experience outcomes | Что больше повторений и больше декора всегда лучше |
| Экономически одинаковый endowed progress дал 34% completion против 19% в car-wash field experiment | E1 | Что для goal gradient обязательно увеличивать награду |

## Что видно только после сопоставления

1. **Публичных E1-данных у российских commercial cases нет.** Самые сильные
   сигналы — сопоставимая когорта «Магнита» и нераскрытые A/B-направления Ozon;
   они полезны для гипотез, но не для параметра uplift.
2. **Почти все эмоциональные продукты всё равно поддержаны cash-like value.**
   Панда, эльф, город и сюжет идут рядом со скидкой, баллами, товаром за 1 ₽ или
   шансом. Из открытых данных нельзя узнать, что останется без неё.
3. **Наиболее близкие X5 кейсы наименее визуально игровые.** Tesco, Carrefour и
   ВкусБэк превращают транзакционную историю в goal/progress/choice; это не
   делает их автоматически лучшими, но яснее связывает механику с поведением.
4. **Сильная non-cash мотивация опирается на существующий job.** У Duolingo это
   learning, у Nike — running, у beauty — discovery/identity. Для grocery такую
   самостоятельную полезность нужно сначала найти у сегмента, а не нарисовать.
5. **Retired/changed cases дают разные уроки.** Odyssey — сложность и узкая beta;
   FuelBand — hardware burden; Walgreens — proxy/fatigue; Сбер — complexity;
   «Плюс Сити» — continuity cost; Monopoly — fraud governance. Единого
   объяснения «геймификация не работает» нет.
