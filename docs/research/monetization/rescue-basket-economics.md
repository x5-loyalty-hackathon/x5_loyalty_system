# «Спасённая корзина»: экономика поверх существующей уценки

> **Scope note · 2026-09-03:** после командного обсуждения current PoC перешёл к
> recipe-first корзине без отдельной брони и заранее собранного физического
> набора. Этот документ сохраняется как подробная проверка
> `reservation/transparent bundle`-альтернативы и её baseline economics, но не
> является текущей UX-спецификацией. Актуальный цикл:
> [X5 Домовой × recipe-first «Спасённая корзина»](../persona_vxofi/rescue-domovoi-concept.md).

- **Статус:** исследовательский отчёт; не решение команды и не доказанный
  business case.
- **Дата проверки источников:** 2026-09-03.
- **Нативные единицы:** `item-batch`, `lot/order`, `store-week`.
- **Цель:** проверить, остаётся ли инкрементальная ценность после уже
  существующих уценки, фудшеринга, передачи фермерам и утилизации.

Метки утверждений:

- **FACT** — прямо следует из источника;
- **INFERENCE** — вывод из фактов, требующий проверки на данных X5;
- **HYPOTHESIS** — предлагаемая продуктовая или экономическая гипотеза;
- **E1** — первичный источник X5 или регулятора;
- **E2** — рецензируемое исследование с раскрытым методом;
- **E3** — авторитетное отраслевое сообщение, но не первичный материал X5.

## Короткий ответ

**INFERENCE.** У идеи есть более короткий путь к деньгам, чем у чистой игры:

```text
единица с высоким P(низкоценного исхода без вмешательства)
→ оплаченная и выкупленная персональная бронь
→ rescue contribution выше ожидаемого baseline
→ плюс только реально инкрементальная маржа сопутствующей корзины
→ минус сборка, сервис, каннибализация, fraud и induced over-ordering
```

Но первоначальная формулировка «любая выручка выше нуля инкрементальна» неверна.
Без новой механики товар мог быть продан по полной цене или с текущей уценкой,
передан на фудшеринг/корм с ненулевой остаточной ценностью или только затем
утилизирован. Новый набор выгоден лишь относительно **взвешенной смеси этих
взаимоисключающих исходов**.

Самый правдоподобный incremental delta — не ещё одна скидка и не непрозрачный
surprise bag, а связка:

1. экономический отбор партий, которые с высокой вероятностью не реализуются
   существующими каналами;
2. точное персональное matching и исключение вероятной органической покупки;
3. бронь конкретного состава и окна выдачи;
4. ограниченный прозрачный bundle, который помогает пристроить несколько
   совместимых позиций;
5. опциональный игровой слой, который должен отдельно доказать прирост
   `reservation → pickup` или повторного использования относительно такого же
   неигрового интерфейса.

**Предварительный вердикт:** сильный кандидат на **money engine**, но пока не
доказанный самостоятельный игровой продукт. Главный риск — после текущей уценки
и альтернативных каналов останется слишком мало стабильного, действительно
инкрементального пула, а сборка и каннибализация поглотят salvage value.

## 1. Verified baseline X5

### 1.1. Уценка и контроль сроков

| Статус | Публично подтверждённый baseline | Значение для идеи |
|---|---|---|
| **FACT, E1, 2019** | X5 сообщала, что товары с истекающим сроком в «Пятёрочке» получают специальную маркировку, а цена в среднем снижается на **20–40%**. Одновременно компания уже называла прогноз спроса, увеличение частоты поставок, адаптацию ассортимента и уменьшение кванта поставки способами сокращать отходы. [X5, 07.11.2019](https://www.x5.ru/ru/news/pyatyorochka-nachala-otdavat-nereali/) | «Прогнозируем списание» и «уценяем near-expiry» сами по себе не являются новизной. |
| **FACT, E3, 2025–2026** | Retail.ru со ссылкой на данные АКОРТ/X5 пишет, что для готовых блюд Data Matrix автоматически применяет **скидку 50% за два дня** до окончания срока и блокирует просроченный товар. [Retail.ru, 17.03.2026](https://www.retail.ru/news/akort-chislo-laboratornykh-proverok-v-torgovykh-setyakh-vyroslo-za-god-na-10-17-marta-2026-275609/) | Указанные командой «до 50%» подтверждаются для конкретного контура готовой еды, но не как единое правило всех SKU и всех сетей. Это baseline для пилота, а не новый reward. |
| **FACT, E1, август 2026** | «Свежая полка» в «Перекрёстке» отслеживает партии по цифровой маркировке, подсказывает сотруднику проверить, уценить или снять товар, блокирует продажу просроченного; сниженные предложения доступны в магазине и приложении. X5 заявляет высвобождение до **60% времени сотрудников**, но не раскрывает метод расчёта. [X5 Media, 2026](https://mediahub.x5.ru/news/perekryostok-zapustil-sistemu-kontrolya-srokov-godnosti-tovarov-svezhaya-polka) | Простое отображение уценки в приложении также уже не выглядит новизной. Нужны reservation, matching или bundle с измеримой добавкой. |
| **FACT, E1, 13.08.2026** | «Пятёрочка» начала по данным «Честного знака» предупреждать покупателя уже приобретённого товара о приближении срока: например, молочку за три дня, детское питание за пять. [X5 Media](https://mediahub.x5.ru/news/pyatyorochka-zapuskaet-servis-kotoryj-napomnit-o-sroke-godnosti-produktov) | X5 уже может связывать отдельную маркированную единицу, чек и пользователя. После покупки можно снижать consumer waste, но это другой эффект, его нельзя считать спасением магазинного остатка. |

**FACT, E1.** Продажа товара после срока годности запрещена; до срока продавец
может снижать цену. [Роспотребнадзор](https://04.rospotrebnadzor.ru/index.php/consumer-information/faq/3975-30012015.html).
Это жёсткая граница: бронь, сборка и выдача должны завершаться до срока с
достаточным окном безопасного домашнего использования.

**Ограничение evidence по 50%.** Первичный материал X5 подтверждает функции
«Свежей полки» и сниженные цены, но на проверенной странице не указывает глубину
скидки. Поэтому `50% за два дня` — **E3 для готовой еды**, а не доказанная
федеральная политика всего X5. До расчёта пилота кейсодатель должен подтвердить
по категориям `markdown_depth`, `markdown_start` и `markdown_sell_through`.

### 1.2. Фудшеринг, передача фермерам и утилизация

| Статус | Публичный факт | Что нельзя из него выводить |
|---|---|---|
| **FACT, E1, 2024** | X5 указывает более **300 т** продуктов, переданных через фудшеринг, в контуре более 10 городов, 62 магазинов, 11 дарксторов и 1 РЦ. [X5: продовольственная помощь](https://esg.x5.ru/ru/programs/food-aid/) | Нельзя считать весь объём предотвращённым списанием без item-level baseline. Отдельные `>1 000 т` «Корзины доброты» — купленные/собранные пожертвования, не остатки X5. |
| **FACT, E1, 2022–2023** | В первом пилоте сотрудники ежедневно отбирали хлеб за 1–2 дня до срока, волонтёры забирали его в тот же день. X5 сообщила о снижении списаний хлеба в участвующих магазинах в среднем на **25%**, без опубликованного экспериментального дизайна. [X5](https://esg.x5.ru/ru/news/250723/) | Это E1-корпоративный результат, но не переносимый uplift для новых категорий, магазинов или платной rescue-механики. |
| **FACT, E1, 2024** | «Пятёрочка» и «Перекрёсток» передали фермерам более **122 тыс. т** нереализованной продукции/продуктов, утративших товарный вид до срока. [X5: отходы](https://esg.x5.ru/ru/programs/waste-reduction/) | Передача фермеру уже является baseline-исходом с собственной логистикой и возможной ценностью; её нельзя одновременно назвать disposal и avoided disposal. |
| **FACT, E1, 30.06.2025** | Для программы «Пятёрочки» X5 сообщает более **457 тыс. т** накопительно с 2019 года, 7 100 фермеров и ежедневную сортировку овощей, фруктов, хлеба, бакалеи и молочки. [X5](https://esg.x5.ru/ru/news/300625/) | Накопительный объём нельзя складывать с показателем 122 тыс. т за 2024 год. Публичный материал не раскрывает net proceeds и стоимость операции. |
| **FACT, E1, проверено 03.09.2026** | X5 пишет, что часть пищевых отходов передаётся сторонним компаниям для утилизации/захоронения, параллельно тестируются переработка, корм, удобрения и биогаз. [X5](https://esg.x5.ru/ru/programs/waste-reduction/) | Не опубликованы стоимость утилизации на единицу и доля каждого исхода, поэтому `avoided_disposal` пока параметр, не готовая выгода. |
| **FACT, E1, 29.04.2026** | В совместном материале X5/СКОЛКОВО указано, что НДС на благотворительную передачу и длительные ветеринарные проверки делают фудшеринг экономически менее выгодным; утилизация может быть дешевле передачи. [X5](https://esg.x5.ru/ru/news/29042026/) | Donation нельзя считать бесплатным нулевым исходом. Налоговую и ветеринарную модель обязан подтвердить профильный специалист X5 для конкретных категорий. |

**INFERENCE.** Масштаб передаваемых фермерам товаров на порядки выше публичного
масштаба фудшеринга. Это доказывает большой уже организованный non-sale/fallback
pool, но **не доказывает**, что тот же объём безопасен, юридически допустим,
пригоден по оставшемуся сроку и экономически addressable для продажи людям.
Rescue-продукт должен сначала измерить пересечение этих условий и отбирать
только те единицы, где платная реализация после всех затрат лучше **конкретного
текущего fallback**, а не сравниваться с воображаемым «всё выбросили».

### 1.3. Контекст кейса

**FACT, внутренний первичный контекст, 2026-09-03.** В `qa_session.md` автор
кейса Kiruxa сообщил, что существующие игры страдают от длинного пути,
практически нулевых MAU/retention и слабых призов; наличие ML/AI само по себе не
критично, важнее соответствие задаче, практическая ценность, обоснованность,
прототип и следующий шаг. Числа сегментов в той же сессии были сгенерированы
совместно с Cursor и не являются измеренным профилем X5.

**INFERENCE.** Для rescue-концепта главный demo должен быть не «AI красиво
собрал коробку», а `точная партия → baseline outcome → экономический gate →
бронь → pickup → фактический contribution`. Игра не должна удлинять путь к
понятной выгоде.

## 2. Почему списание остаётся даже при скидке 50%

### Подтверждённые причины на уровне модели рынка

1. **Demand uncertainty и цена отсутствия товара.** Ритейлер заказывает до
   реализации спроса и балансирует stockout против waste. Эмпирико-структурная
   работа на категории хлеба американской сети показывает, что более высокая
   неопределённость и цена stockout связаны с большим «planned waste».
   [Sanders, Marketing Science, опубликовано 2023, E2](https://pubsonline.informs.org/doi/10.1287/mksc.2020.0214)
2. **Одинаковая скидка не соответствует разной эластичности.** В той же работе
   оптимальная динамическая цена в контрфактической симуляции дала `−20,82%`
   waste и `+2,88%` category gross profit относительно оптимальной статичной
   цены, но эффект сильно различался по `store × product`, а фиксированная
   стоимость внедрения могла поглотить прибыль. Это не uplift X5 и не base-case.
3. **Покупатель ценит оставшийся срок нелинейно.** Revealed-preference
   исследование европейского ритейлера выявило нелинейную willingness-to-pay за
   дни свежести и дополнительное снижение воспринимаемой ценности от самого
   markdown label. [Sousa et al., 2025, E2](https://doi.org/10.1016/j.samod.2025.100040)
4. **Clearance может менять предложение и переносить отход домой.** Модель
   surprise clearance показывает: распродажа может увеличить прибыль магазина,
   но стимулировать больший объём производства и увеличить consumer waste;
   эффект зависит от маржи, ценности потребления и однородности содержимого.
   [Yang & Yu, Management Science, 22.07.2025, E2](https://pubsonline.informs.org/doi/full/10.1287/mnsc.2023.03001)

### Friction map для X5, который нужно валидировать

| Возможная причина остатка | Статус | Что проверить в данных |
|---|---|---|
| Скидка начинается слишком поздно или слишком мала для конкретного `SKU × store × day` | **INFERENCE** | sell-through по часу, глубине скидки, остатку и remaining shelf life |
| Товар не замечают; приложение показывает предложение, но не гарантирует наличие конкретной единицы | **INFERENCE** | impressions → store visit → scan; cancellation из-за stock mismatch |
| Нет брони, поэтому пользователь не идёт специально за товаром с риском, что его забрали | **HYPOTHESIS** | stated intent недостаточен; нужен reservation A/B |
| Состав общего остатка не соответствует рациону/объёму домохозяйства | **INFERENCE** | category affinity, повторная покупка, жалобы, household consumption proxy |
| Универсальные 50% каннибализируют органическую покупку, поэтому ещё более ранняя/глубокая уценка нерентабельна | **INFERENCE** | regular-price displacement и ожидание скидки в горизонте consumption cycle |
| Foodsharing ограничен категориями, географией, волонтёрской логистикой, налогом и проверками | **FACT + INFERENCE** | eligible share по категории/городу, tax/logistics cost, pickup reliability фонда |
| Передача фермерам лучше захоронения, но не даёт consumer revenue | **FACT + INFERENCE** | net salvage каждого договора, труд, график вывоза |
| Сборка, маркировка, холодовая цепь и короткое окно делают мелкие остатки экономически непригодными | **INFERENCE** | минуты работы и cost-to-serve на item/lot, time-to-expiry after pickup |

Итого: существование списаний поверх 50% не доказывает спрос на новый продукт.
Оно лишь показывает остаточный пул, внутри которого надо найти единицы с
положительным `rescue value − expected baseline value`.

## 3. Incremental delta и отличия от текущей уценки

### 3.1. Минимум пять содержательных отличий

| Текущий baseline | Предлагаемая добавка | Предполагаемый delta | Как изолировать |
|---|---|---|---|
| Time-based markdown, в подтверждённом контуре готовой еды — 50% за два дня | **Economic eligibility:** прогноз не только списания, а взаимоисключающих исходов `full / markdown / donation / recovery / disposal` | Не отдавать дешевле товар, который ещё продаст текущая уценка; направлять усилие на низкоценный остаток | Shadow replay против действующего правила |
| Уценённое предложение на полке/в приложении | **Exact reservation:** конкретный состав, срок и окно pickup; единый токен | Снижает риск пустого визита и превращает digital intent в измеримый заказ | Control vs same price + reservation |
| Общая витрина | **Matching:** история категорий, домашний магазин, объём; исключение вероятной organic full-price покупки | Выше conversion при меньшей каннибализации и consumer waste | Non-personalized reservation vs personalized, цена и inventory одинаковы |
| Отдельные уценённые позиции | **Transparent dynamic bundle:** 2–3 совместимых сценария еды, точный состав и даты, ограниченный размер | Пулит слабые позиции и уменьшает search cost без mystery-box риска | Item reservation vs transparent bundle |
| Скидка заканчивается на кассе | **Pickup-verified recipe/world layer:** продукты отражаются в цифровом доме, предлагается сохранённый рецепт и необязательные complementary items | Возможная повторяемость и companion margin | Такой же utility UI vs utility + game при одинаковом offer |

**Важно.** `Показать уценку в приложении`, `предсказать near-expiry` и
`автоматически заблокировать просрочку` уже находятся в публичном baseline X5.
Их нельзя защищать как самостоятельную новизну.

### 3.2. Варианты продукта по сложности

1. **V1 — бронь отдельных позиций.** Точный SKU/партия/срок, цена, короткое
   окно. Минимум сборки, максимальная диагностичность. Самый разумный RAT-пилот.
2. **V2 — прозрачная персональная корзина.** Несколько совместимых единиц,
   точный состав, общий номинал; собирается только после оплаченной брони.
   Может поглотить больше слабого пула, но добавляет труд и риск stock mismatch.
3. **V3 — dynamic meal bundle.** Rescue-ядро плюс 1–2 явно помеченных обычных
   complementary items для конкретного рецепта. Это самый прямой route к
   companion margin, но его нельзя маскировать общей «выгодой набора».
4. **V4 — rescue mission.** После pickup покупка отражается в постоянном мире,
   рецепт сохраняется; игровой результат не меняет цену, срок или состав.
   Добавлять только отдельной экспериментальной рукой после жизнеспособности V1.

**Предварительная приоритизация:** `V1 → V2/V3 → V4`. Попытка сразу запустить
персональный bundle, ML, бронь, рецепты и игру скроет, какой компонент заработал,
и максимально нагрузит магазин.

## 4. Eligible event, user job и game job

### Eligible inventory

**HYPOTHESIS.** Единица допускается только если одновременно:

- известны партия, срок, остаток, текущая уценка и доступный fallback;
- после pickup остаётся согласованный safe-use window;
- `expected_rescue_contribution > expected_baseline_contribution + risk_buffer`;
- вероятность продажи данному пользователю по полной цене в естественном окне
  ниже лимита;
- товар совместим с заявленными исключениями и историей категорий; чувствительные
  медицинские выводы не строятся;
- объём набора соответствует proxy домохозяйства;
- категория допущена food-safety/legal командой.

### Eligible user

**HYPOTHESIS.** Digital-пользователь с домашним магазином, достаточной историей,
покупками в релевантных категориях и не максимальной текущей частотой. На старте
исключаются сотрудники пилотных магазинов, high-velocity promo abuse, несколько
связанных аккаунтов и пользователи с систематическими no-show.

Персонализируется **ranking и состав, но не цена эквивалентной партии**. Это
снижает риск непрозрачной персональной ценовой дискриминации.

### User job

> Получить заранее известную и действительно нужную еду дешевле, не искать
> жёлтые ценники и не рисковать пустым походом, при этом успеть безопасно её
> использовать.

### Game job

Игра имеет право на существование только если выполняет одну из трёх работ:

1. повышает conversion релевантного rescue-offer в оплаченную бронь;
2. снижает no-show через понятную миссию и состояние pickup, не через штрафной
   streak или тревогу;
3. повышает повторное использование или инкрементальную companion margin через
   сохранённый рецепт/историю мира.

**HYPOTHESIS.** Наиболее связный вариант: после pickup точные продукты
«приезжают» в дом персонажа; пользователь получает подходящий проверенный рецепт,
может сохранить его, а недостающие обычные ингредиенты видит отдельно. Короткий
post-pickup `cash out / risk current cosmetic win` допустим как тестируемый
entertainment-layer: рискуется только несохранённый виртуальный результат
текущей сессии, не еда, не скидка и не баллы X5.

**Kill для игры:** если V4 не улучшает contribution/pickup/repeat относительно
того же V2/V3 без игры, игра удаляется; экономическое ядро не обязано погибать.

Неприемлемо:

- скрывать состав или срок ради suspense;
- стимулировать купить больший объём еды ради редкости;
- выдавать rescue-товар за «бесплатный приз»;
- начислять прогресс за резерв без pickup;
- смешивать ESG-метрику магазина и неподтверждённое «вы спасли еду от свалки».

## 5. Unit economics без двойного счёта

### 5.1. Взаимоисключающий baseline одного item-batch

После того как единица уже закуплена и находится в магазине, без новой механики
она может завершить период ровно в одном состоянии:

| Состояние `a` | Post-stock value `V_i(a)` | Что требуется |
|---|---|---|
| `F`: full-price sale | net receipt полной цены минус инкрементальный cost-to-sell | факт продажи, цена, комиссии |
| `M`: existing markdown sale | net markdown receipt минус маркировка/операции | фактическая глубина, время и sell-through |
| `D`: donation / foodsharing | возможная salvage value минус налог, проверки, сбор и логистика | считать donation и feed раздельно |
| `A`: feed / compost / other recovery | договорная выручка или экономия минус сортировка/хранение/вывоз | net value конкретного контрагента |
| `W`: disposal / destruction | `− removal − disposal − documentation` | только реально понесённые переменные затраты |

Обозначим вероятности исходов действующего процесса до момента intervention:

```text
pF_i + pM_i + pD_i + pA_i + pW_i = 1

B_i = pF_i·V_i(F)
    + pM_i·V_i(M)
    + pD_i·V_i(D)
    + pA_i·V_i(A)
    + pW_i·V_i(W)
```

`B_i` — expected baseline value, а не ноль.

### 5.2. Инкрементальная экономика lot/order

Для набора `L` из конкретных единиц:

```text
Delta_inventory(L)
  = rescue_net_receipt(L)
  - pick_pack_scan_cost(L)
  - payment_support_claim_cost(L)
  - expected_fraud_and_quality_loss(L)
  - Σ[i in L] B_i
```

Полный effect заказа:

```text
Delta_order
  = Delta_inventory
  + incremental_companion_margin
  - displaced_regular_margin
  - no_show_and_cancellation_cost
  - game_variable_cost
  - induced_extra_ordering_and_waste_cost
```

Здесь `displaced_regular_margin` — только потеря **будущих покупок вне единиц
`L`**, например замещение следующим набором обычной покупки той же категории.
Opportunity cost full-price/markdown продажи самих единиц `L` уже находится в
`Σ B_i`; повторно включать её в `displaced_regular_margin` нельзя.

`avoided disposal` уже присутствует **один раз**: когда baseline был `W`,
`V_i(W)` отрицателен и вычитается из `B_i`. Нельзя поверх этой формулы ещё раз
добавлять `saved disposal` или «спасённую себестоимость».

COGS уже закупленной единицы можно исключить из post-stock сравнения, потому что
он одинаков во всех исходах и сокращается. Если расчёт ведётся от закупки до
финального P&L, COGS включается **во все** состояния одинаково. Если новый канал
стимулирует сеть заказать/произвести больше товара, COGS и waste дополнительных
единиц добавляются отдельным `induced_extra_ordering` — это следует из риска,
показанного Yang & Yu.

### 5.3. Break-even

```text
rescue_net_receipt + incremental_companion_margin
  >= Σ baseline_item_value
   + all_rescue_variable_costs
   + displaced_regular_margin
   + induced_extra_ordering_loss
```

Или максимальная допустимая стоимость сборки:

```text
max_pick_pack_cost
  = rescue_net_receipt
  + incremental_companion_margin
  - Σ baseline_item_value
  - other_variable_costs
  - cannibalization
  - risk_buffer
```

Если правая часть неположительна, bundle нельзя создавать, даже если он снижает
видимое магазинное списание.

### 5.4. Store-week и нормализация

```text
Net_store_week
  = Σ picked_orders Delta_order
  - reserved_not_picked_cost
  - store_training_and_equipment_amortization
  - incremental_store_marketing
```

```text
Net_1000_eligible_30d
  = 1000 · offers_per_user
    · P(reserve | offer)
    · P(pickup | reserve)
    · E[Delta_order | pickup]
  - 1000 · offers_per_user
    · P(reserve) · P(no_show | reserve) · E[no_show_cost]
  - allocated_fixed_cost
```

Нормализованный показатель сравнивается с другими идеями, но решение о rollout
принимается по фактическому `Net_store_week` и общему contribution пилотных
магазинов.

## 6. Parameter dictionary и сценарии

| Параметр | Единица | Как получить, не выдумывая |
|---|---:|---|
| `eligible_units` | шт./store-day | replay партий после всех текущих eligibility rules |
| `pF, pM, pD, pA, pW` | probability/item | исторические competing-risk outcomes на фиксированном intervention timestamp |
| `markdown_price`, `sell_through` | ₽ net, % | POS + markdown log по часу и партии |
| `recovery_net_value` | ₽/кг или ₽/unit | договоры, сортировка, вывоз; отдельно feed/compost |
| `donation_net_value` | ₽/unit | tax, vet, фонд, labor; не приравнивать нулю |
| `disposal_cost` | ₽/unit или ₽/кг | счета операторов + труд + документы |
| `rescue_price` | ₽/lot | экспериментальная цена net of tax/fees |
| `pick_pack_scan_minutes` | min/lot | time-and-motion pilot, медиана и p90 |
| `labor_rate` | ₽/min | fully loaded store labor |
| `reservation_rate` | % offer | ITT по назначенной группе, не по открывшим приложение |
| `pickup_rate` | % reserve | платная и бесплатная бронь раздельно |
| `stock_mismatch` | % reserve | отмена магазином из-за отсутствия/несоответствия партии |
| `companion_margin_inc` | ₽/pickup | test-control по тому же окну; не весь companion basket |
| `regular_margin_loss` | ₽/user-period | full-price/markdown displacement в consumption-cycle window |
| `consumer_waste_proxy` | %/lot | добровольная короткая обратная связь + повторная покупка; не считать доказательством |
| `complaint_refund_loss` | ₽/lot | claims, refund, service и reward reversal |
| `fraud_loss` | ₽/lot | подтверждённые loss cases, не просто risk score |
| `availability_days` | % planned days | дни, когда собирается экономически допустимый набор |

До реальных данных числа не подставляются. Сценарии задаются направленно:

| Scenario | Baseline sale value | Pickup/companion | Labor/fraud | Cannibalization |
|---|---|---|---|---|
| pessimistic | высокий markdown/full-price sell-through | низкие | высокие | высокая |
| base | posterior/holdout historical estimate | pilot posterior | time study | causal estimate |
| optimistic | высокий `pW` и низкий recovery value | высокие | низкие | низкая |

Внешние `−20,82% waste`, `+2,88% gross profit` и другие эффекты не переносятся
в base-case X5.

## 7. Operational map

```text
Fresh Shelf / Data Matrix / stock / markdown log
                 ↓
freeze baseline decision timestamp
                 ↓
competing-risk forecast F/M/D/A/W + confidence
                 ↓
economic eligibility gate + food-safety rules
                 ↓
matching user ↔ exact eligible inventory
                 ↓
V1 exact item OR V2 transparent constrained bundle
                 ↓
paid reservation / short TTL / single-use token
                 ↓
staff scans exact units only after reservation
                 ↓
pickup before safety deadline + receipt reconciliation
                 ↓
actual outcome ledger / claims / fallback route
                 ↓
optional recipe/world event after verified pickup
```

### Обязательные операции, которые нельзя спрятать за UI

1. **Inventory truth.** Нужны партия, срок и остаток почти в реальном времени.
   Если точной единицы нет, магазин отменяет и возвращает оплату; подмена требует
   нового согласия пользователя.
2. **Economic freeze.** Вероятности baseline считаются до показа предложения,
   иначе модель обучится на собственном intervention и назовёт результат
   органическим.
3. **Assembly on demand.** Набор собирается после брони, чтобы не тратить труд на
   невыкупленный лот. Для ультракороткого срока может потребоваться pre-assembly;
   это отдельная операция и cost arm.
4. **Cold chain and safe-use buffer.** В pickup deadline входит время сборки и
   домашнего использования, а не только формальное «ещё не просрочено».
5. **Fallback.** При отсутствии брони единица возвращается в действующий путь:
   markdown → foodsharing/recovery → disposal по правилам категории. Rescue не
   должен блокировать более ценный исход.
6. **Accounting.** В чеке отдельно видны rescue items и обычные complement;
   отчётность сохраняет исходную партию и markdown history.
7. **Service.** Жалоба на качество и законный возврат не ухудшают fraud score
   автоматически. Game reward сначала `pending`, затем финализируется после
   reconciliation.

### Данные, которых нет в исходном PoC

- batch/expiry-level on-hand и история корректировок;
- timestamps текущей уценки и фактические исходы единицы;
- net value donation/feed/compost/disposal;
- fully loaded store labor и график холодовой цепи;
- фондовые/фермерские ограничения по категориям;
- pre-order/payment/refund API;
- реальные жалобы, no-show, stock mismatch и consumer waste.

## 8. Cannibalization и failure modes

| Риск | Как возникает | Измерение/ограничение |
|---|---|---|
| Full-price displacement | в набор попал товар, который пользователь купил бы сам | exclusion model + категория/SKU margin в следующем consumption cycle |
| Existing markdown displacement | rescue лишь переупаковал уже продающуюся 50%-ную уценку | control = текущий markdown; считать только разницу исходов |
| Time shift | пользователь забрал lot сегодня вместо обычного визита завтра | purchase days и margin на 30/60 дней, не same-day basket |
| Channel shift | приложение забрало покупателя с офлайн жёлтого ценника | total user/store contribution across channels |
| Donation/recovery displacement | коммерческий lot вытеснил более выгодный договор или социальный объём | отдельный baseline state и ESG guardrail |
| Consumer waste | дешёвый объём не съеден дома | небольшие наборы, affinity, feedback; не заявлять saved kg без подтверждения |
| Strategic waiting | покупатель учится ждать rescue | holdout, stochastic eligibility, limit; не обещать ежедневную одинаковую скидку |
| Induced over-ordering | новый outlet снижает цену ошибки прогноза заказа | order quantity и total waste против контроля; bonus владельца процесса от total contribution |
| Cherry-picking | лучшие остатки уходят, слабые остаются | bundle constraints, но точный состав до оплаты обязателен |
| No-show/hoarding | бесплатная бронь блокирует последние часы продажи | prepay или короткий TTL, household cap, cooldown после подтверждённых no-show |
| Operational rejection | персонал не успевает найти/собрать | minutes/lot p90, максимум позиций, scan route, kill by labor break-even |
| Trust collapse | плохой срок, подмена или «сбыт неликвида» | дата и состав до оплаты, auto-refund, complaint non-inferiority |

## 9. Pilot: сначала utility, потом game

### 9.1. До пилота — shadow replay

На 8–12 неделях истории нескольких форматов магазинов:

1. фиксируем момент, когда система могла бы принять решение;
2. оцениваем competing risks `F/M/D/A/W` действующего процесса;
3. применяем eligibility и constrained bundle;
4. считаем доступные `lots/store-day`, `availability_days`, expected delta и
   чувствительность к ошибке прогноза;
5. сравниваем с правилами `2 дня / 50%`, remaining-life threshold и oracle;
6. отдельно делаем time-and-motion без клиентского запуска.

Модель проверяется time-based holdout и калибровкой вероятностей, а не только
ROC-AUC. Решение зависит от expected value, поэтому нужны calibration error и
policy value against baseline.

### 9.2. Кластерный component test

Рекомендуемые руки при достаточном числе matched stores:

| Arm | Что получает магазин/пользователь | Какой delta изолирует |
|---|---|---|
| `C` | текущая «Свежая полка» / markdown / fallback | baseline |
| `T1` | та же цена и inventory + exact digital reservation | ценность брони |
| `T2P` | `T1` + personalized ranking отдельных позиций | matching без pooling |
| `T2B` | `T1` + неперсонализированный transparent bundle | pooling без matching |
| `T2PB` | `T1` + personalization + transparent bundle | interaction двух компонентов |
| `T3` | лучший utility-arm + recipe/world/rescue mission | собственно game layer |

Если числа точек не хватает, сначала сравнивается `T2PB` с `T1`, но результат
честно относится ко всему пакету; personalization и pooling после сигнала
разделяются факториальным `2×2`. Нельзя приписать общий эффект `T2PB` модели
matching.

Рандомизация — matched store clusters или store-week switchback с washout,
потому что пользователи конкурируют за конечный пул. Чистая индивидуальная A/B
рандомизация нарушает SUTVA: treatment одного пользователя лишает inventory
другого. Матчинг: формат, регион, traffic, markdown sell-through, waste,
категорийный mix, штат и foodsharing/recovery route. Saturation пользователей и
число offers фиксируются заранее.

### Primary metric

```text
fully_loaded_incremental_contribution_per_store_week
```

Считается по всем каналам и включает baseline value inventory, труд,
refund/claims, regular-margin displacement и фактическую companion incrementality.

### Secondary и guardrails

- sell-through eligible item-batches до deadline;
- kg и carrying value, ушедшие в `W`, `D`, `A`, раздельно;
- reservation, pickup, no-show, stock mismatch;
- purchase days и total margin на eligible user за 30/60 дней;
- regular sales/margin вне rescue;
- minutes/lot median и p90;
- complaints/refunds and food-safety incidents;
- доля дней с реальным предложением;
- заказанный объём и total store + reported consumer waste;
- `T3 − best utility arm`: contribution, pickup и repeat; MAU сам по себе не
  primary.

## 10. RAT и kill criteria

### Riskiest assumption

**HYPOTHESIS / RAT.** После текущих 50%-ных markdown и fallback-каналов на
типичной точке остаётся достаточно стабильный пул партий, для которых
оплаченная бронь даёт положительный fully loaded delta, не вытесняя органическую
продажу и не увеличивая заказ/домашние отходы.

### Самый дешёвый тест

Shadow replay `item-batch × store × hour` плюс time-and-motion. Это дешевле UI и
закрывает сразу объём, регулярность, baseline value, необходимость ML и предел
допустимого труда. Если нет batch-level outcomes, следующий шаг — не модель, а
двухнедельный ручной журнал на малом числе точек.

### Kill / simplify

Идея закрывается или упрощается, если выполняется любое:

1. нижняя граница согласованного интервала `Net_store_week` ≤ 0 после всех
   переменных затрат и каннибализации;
2. conservative scenario отрицателен даже при нулевой стоимости игры;
3. экономически допустимый pool не собирает минимальную заранее заданную
   доступность (например, **иллюстративно** 4 из 7 дней; порог выбирает команда
   по нужной cadence, это не факт X5);
4. utility arms не снижают state `W` или лишь вытесняют существующую markdown
   sale;
5. regular contribution падает сильнее pre-registered non-inferiority margin;
6. p90 труда на lot выше break-even `max_pick_pack_minutes`;
7. stock mismatch/no-show оставляет меньше времени более ценному fallback;
8. quality complaints выходят за safety/non-inferiority boundary;
9. order quantities или total waste растут — магазинное списание просто
   перенесено домой либо создано дополнительным заказом.

Для игрового слоя отдельный simplify criterion: `T3` не лучше лучшего utility
arm по net contribution/pickup/repeat — убрать игру, а не приписывать ей общий
эффект V2.

## 11. Basic antifraud и control surface

### Основные сценарии

- массовая бронь дефицитных лотов и no-show;
- несколько X5ID/устройств/платёжных средств одного домохозяйства;
- перепродажа и bulk acquisition;
- повторное использование pickup token или replay запроса;
- фиктивный pickup/ручная подмена состава сотрудником;
- возврат/complaint после получения игрового результата;
- collusion сотрудника и пользователя, ручное занижение baseline value;
- split receipts ради нескольких миссий.

### Минимальные правила

1. один active reservation на household/store/window; cap по дням и объёму;
2. prepaid exact order либо короткий TTL; progressive cooldown только после
   подтверждённых no-show;
3. single-use signed token, idempotent reserve/pickup/refund;
4. scan каждой партии при сборке и выдаче; composition hash и reason code любой
   подмены;
5. reward только после verified pickup, затем hold до reconciliation;
6. device/account/payment/phone cluster, velocity, repeated store-employee pair,
   abnormal quantity и graph features;
7. `allow / review / block` с precision-first threshold и reason codes;
8. immutable event log решений модели, сотрудника, платежа и награды;
9. refund/жалоба по качеству не является fraud сама по себе и не ограничивает
   права потребителя;
10. store-level manual override имеет отдельное разрешение и аудит.

Главный fraud KPI — подтверждённая loss rate, false-positive complaints и ручная
нагрузка, а не доля заблокированных заказов.

## 12. Что честно показывает PoC

### Можно показать

- synthetic item-batch inventory и пять взаимоисключающих baseline outcome;
- calibrated risk model / survival or competing-risks policy;
- economic gate и constrained transparent bundle;
- объяснение пользователю: состав, срок, цена, почему подходит;
- 3–4 экрана: offer → exact contents/reserve → pickup token → verified
  recipe/world event;
- таблицу sensitivity по baseline sell-through, labor, pickup,
  cannibalization и companion margin;
- антифрод-скоринг no-show/replay/multi-account с precision-first threshold;
- power/design пилота и логи решений.

### Нельзя доказать

- реальный объём и стабильность остаточного pool X5;
- causal uplift частоты, companion margin или игры;
- реальную точность on-hand/expiry и выполнимость сборки;
- food-safety и юридическую допустимость категорий;
- стоимость donation/feed/disposal;
- сокращение total food waste, особенно дома;
- что ML бьёт действующую «Свежую полку».

Synthetic генератор не должен создавать inventory той же моделью, которую потом
«успешно» оценивает. Нужны независимые сценарии data-generating process и
stress-tests.

AI не обязателен по Q&A. Если он используется, наиболее честная роль —
competing-risk forecast, matching и объяснение из проверенных reason codes.
Цена, food-safety gate и blocking остаются детерминированными.

## 13. Hard gates: предварительная оценка

| Gate | Статус | Обоснование |
|---|---|---|
| G1 Money route | **conditional pass** | salvage delta item/lot и companion margin имеют короткую формулу |
| G2 Counterfactual | **pass in design** | заданы mutually exclusive `F/M/D/A/W`; нужны реальные логи |
| G3 Incrementality | **pass in design** | current-markdown control и component cluster arms |
| G4 Margin guardrail | **pass in design** | break-even сборки/цены/cannibalization явно вычислим |
| G5 Pilotability | **weak/conditional** | требует batch truth, store ops, payments, safety и нескольких точек |
| G6 Game fit | **not yet passed** | игра пока гипотеза; обязана победить одинаковый utility-only arm |
| G7 User value | **conditional pass** | точная выгода + бронь + прозрачность; зависит от состава и safe-use window |
| G8 Risk boundary | **conditional** | базовый control surface есть; food safety и право требуют профильной проверки |

## 14. Вопросы кейсодателю/X5 до защиты

1. Для каких сетей, категорий и регионов реально действует `50% / 2 days`?
2. Есть ли в «Свежей полке» batch-level on-hand, markdown timestamp и конечный
   outcome единицы, или только задачи сотруднику?
3. Можно ли уже бронировать конкретную уценённую единицу в приложении?
4. Какова доля продаж по текущей уценке и disposal после неё по категории?
5. Как бухгалтерски разделяются donation, feed/compost, disposal и markdown;
   каков их net value после труда, налога и логистики?
6. Какие категории допустимы для брони/комплектов и какой safe-use buffer нужен?
7. Есть ли API online payment/refund и норматив времени сборщика магазина?
8. Допустимо ли одинаково уценивать эквивалентную партию, персонализируя только
   показ/состав?
9. Какая store-level primary metric доступна жюри: gross margin, commercial
   margin, EBIT proxy или только revenue/write-off?
10. Обязаны ли финальные 3–4 экрана включать все механики из первоначального
    текста кейса, или Q&A допускает один связный money engine?

## 15. Итог для shortlist

```text
Strongest money engine:
  paid exact reservation of high-P(low-value-outcome) inventory

Strongest utility delta:
  personalized transparent composition + safe pickup window

Strongest direct add-on:
  explicitly separated recipe complement with causal margin measurement

Game role:
  optional pickup/repeat amplifier, component-tested against utility-only

Do not claim:
  «отрицательная стоимость награды»
  «любая lot revenue инкрементальна»
  «каждый проданный lot = столько же предотвращённых отходов»
```

«Спасённая корзина» остаётся перспективнее чистого avatar/game по прямоте P&L,
потому что начинает с существующего актива с падающей opportunity cost. Но
победит она только в случае, если historical replay подтвердит остаточный пул
**после** нынешней уценки и fallback, а пилот покажет положительный fully loaded
delta. До этого это сильная проверяемая гипотеза, а не доказанная экономия.
