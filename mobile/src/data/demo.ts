export type DemoRecipeMode = 'current' | 'repeat' | 'explore';

export interface DemoIngredient {
  id: string;
  name: string;
  category: string;
  amount: string;
  emoji: string;
  defaultAvailable: boolean;
}

export interface RecipeStep { title: string; minutes: number }

export interface DemoRecipe {
  id: string;
  title: string;
  mode: DemoRecipeMode;
  time: number;
  servings: number;
  description: string;
  ingredients: DemoIngredient[];
  steps: RecipeStep[];
  lastCooked?: string;
  note?: string;
}

const ingredient = (
  id: string, name: string, category: string, amount: string, emoji: string, defaultAvailable: boolean,
): DemoIngredient => ({ id, name, category, amount, emoji, defaultAvailable });

export const demoRecipes: DemoRecipe[] = [
  {
    id: 'spaghetti_bolognese', title: 'Спагетти болоньезе', mode: 'current', time: 35, servings: 4,
    description: 'Густой томатный соус с фаршем индейки тушится под крышкой, пока варятся спагетти. Пармезан лучше натереть в самом конце.',
    ingredients: [
      ingredient('pasta', 'Спагетти', 'pantry', '400 г', '〰', true),
      ingredient('mince', 'Фарш индейки', 'meat', '350 г', '◉', true),
      ingredient('tomato', 'Помидоры', 'vegetable', '4 шт.', '●', true),
      ingredient('onion', 'Лук репчатый', 'vegetable', '1 шт.', '◌', false),
      ingredient('cheese', 'Пармезан', 'dairy', '60 г', '◆', true),
      ingredient('basil', 'Базилик свежий', 'herbs', '10 г', '♣', false),
    ],
    steps: [
      { title: 'Обжарить лук до золотистого', minutes: 6 },
      { title: 'Добавить фарш, разбить комочки', minutes: 10 },
      { title: 'Влить томаты, тушить под крышкой', minutes: 12 },
      { title: 'Отварить спагетти al dente', minutes: 7 },
      { title: 'Смешать и посыпать пармезаном', minutes: 2 },
    ],
  },
  {
    id: 'pasta_tomatoes', title: 'Паста с томатами', mode: 'current', time: 20, servings: 2,
    description: 'Быстрая паста со свежими томатами и ароматными травами.',
    ingredients: [
      ingredient('pasta', 'Спагетти', 'pantry', '220 г', '〰', true),
      ingredient('tomato', 'Помидоры', 'vegetable', '3 шт.', '●', true),
      ingredient('basil', 'Базилик', 'herbs', '8 г', '♣', false),
    ],
    steps: [{ title: 'Сварить пасту и приготовить соус', minutes: 20 }],
  },
  {
    id: 'mince_bake', title: 'Запеканка из фарша', mode: 'current', time: 50, servings: 4,
    description: 'Домашняя запеканка из индейки под сырной корочкой.',
    ingredients: [
      ingredient('mince', 'Фарш индейки', 'meat', '400 г', '◉', true),
      ingredient('cheese', 'Сыр', 'dairy', '100 г', '◆', true),
      ingredient('egg', 'Яйца', 'egg', '2 шт.', '⬭', false),
    ],
    steps: [{ title: 'Собрать запеканку и запечь', minutes: 50 }],
  },
  {
    id: 'syrniki', title: 'Сырники', mode: 'repeat', time: 25, servings: 2,
    description: 'Знакомый завтрак с мягким творогом.', lastCooked: 'готовили 4 раза',
    ingredients: [ingredient('cottage_cheese', 'Творог', 'dairy', '300 г', '□', true)],
    steps: [{ title: 'Сформировать и обжарить сырники', minutes: 25 }],
  },
  {
    id: 'cheese_omelette', title: 'Омлет с сыром', mode: 'repeat', time: 10, servings: 2,
    description: 'Быстрый омлет на молоке.', lastCooked: 'готовили 9 раз',
    ingredients: [ingredient('egg', 'Яйца', 'egg', '3 шт.', '⬭', false)],
    steps: [{ title: 'Взбить и приготовить омлет', minutes: 10 }],
  },
  {
    id: 'chicken_soup', title: 'Куриный суп', mode: 'repeat', time: 45, servings: 4,
    description: 'Лёгкий домашний суп.', lastCooked: 'готовили 3 раза',
    ingredients: [ingredient('chicken', 'Курица', 'meat', '350 г', '△', false)],
    steps: [{ title: 'Сварить бульон и добавить овощи', minutes: 45 }],
  },
  {
    id: 'spaghetti_nests', title: 'Гнёзда из спагетти', mode: 'explore', time: 40, servings: 3,
    description: 'Новый способ приготовить пасту.', note: 'нужно 2 продукта',
    ingredients: [ingredient('pasta', 'Спагетти', 'pantry', '300 г', '〰', true)],
    steps: [{ title: 'Собрать гнёзда и запечь', minutes: 40 }],
  },
  {
    id: 'tomato_soup', title: 'Томатный крем-суп', mode: 'explore', time: 30, servings: 3,
    description: 'Яркий крем-суп.', note: 'нужен 1 продукт',
    ingredients: [ingredient('tomato', 'Помидоры', 'vegetable', '500 г', '●', true)],
    steps: [{ title: 'Запечь овощи и пробить блендером', minutes: 30 }],
  },
  {
    id: 'cheese_pie', title: 'Пирог с сыром', mode: 'explore', time: 55, servings: 6,
    description: 'Новый сытный пирог.', note: 'нужно 3 продукта',
    ingredients: [ingredient('cheese', 'Сыр', 'dairy', '250 г', '◆', true)],
    steps: [{ title: 'Замесить тесто и запечь пирог', minutes: 55 }],
  },
  {
    id: 'meatballs', title: 'Фрикадельки', mode: 'explore', time: 35, servings: 4,
    description: 'Нежные фрикадельки из индейки.', note: 'всё есть',
    ingredients: [ingredient('mince', 'Фарш индейки', 'meat', '400 г', '◉', true)],
    steps: [{ title: 'Сформировать и потушить фрикадельки', minutes: 35 }],
  },
];

export interface KitchenProduct {
  id: string; name: string; quantity: string; expires: string; tone: 'good' | 'soon' | 'today';
}

export const kitchenProducts: KitchenProduct[] = [
  { id: 'pasta', name: 'Спагетти', quantity: '450 г', expires: '12 дней', tone: 'good' },
  { id: 'mince', name: 'Фарш индейки', quantity: '400 г', expires: '2 дня', tone: 'soon' },
  { id: 'tomato', name: 'Помидоры', quantity: '500 г', expires: '4 дня', tone: 'good' },
  { id: 'cheese', name: 'Пармезан', quantity: '200 г', expires: '21 день', tone: 'good' },
  { id: 'milk', name: 'Молоко', quantity: '1 л', expires: 'сегодня', tone: 'today' },
  { id: 'bread', name: 'Хлеб', quantity: '400 г', expires: '3 дня', tone: 'good' },
];

export interface CatalogProduct {
  id: string;
  name: string;
  unit: string;
  price: number;
  rating: number;
  /**
   * Уценённый товар: короткий срок годности, цена ниже обычной.
   * Соответствует `source: 'markdown'` в контракте backend.
   */
  markdown?: boolean;
  /** Цена до уценки. Показывается зачёркнутой рядом с текущей. */
  originalPrice?: number;
}

export const readyMeal: CatalogProduct = {
  id: 'ready-bolognese', name: 'Спагетти болоньезе, готовое блюдо', unit: '350 г', price: 249.99, rating: 4.91,
};

export const catalogProducts: CatalogProduct[] = [
  { id: 'macfa-thin', name: 'Спагетти Макфа тонкие', unit: '450 г', price: 89.99, rating: 4.94 },
  { id: 'barilla-5', name: 'Паста Barilla Spaghetti n.5', unit: '500 г', price: 149.99, rating: 4.97 },
  { id: 'shebekinskie', name: 'Спагетти Шебекинские', unit: '450 г', price: 74.99, rating: 4.88, markdown: true, originalPrice: 119.99 },
  { id: 'rollton', name: 'Макароны Роллтон спагетти', unit: '400 г', price: 59.99, rating: 4.71 },
  { id: 'divo', name: 'Спагетти цельнозерновые Диво', unit: '400 г', price: 119, rating: 4.9 },
  { id: 'makfa-nests', name: 'Спагетти Макфа гнёзда', unit: '400 г', price: 69.99, rating: 4.82, markdown: true, originalPrice: 109.99 },
  { id: 'red-price', name: 'Спагетти Красная цена', unit: '450 г', price: 44.99, rating: 4.65 },
];

const alternativeCatalogs: Record<string, CatalogProduct[]> = {
  onion: [
    { id: 'onion-yellow', name: 'Лук репчатый жёлтый', unit: '1 кг', price: 69.99, rating: 4.86 },
    { id: 'onion-packed', name: 'Лук репчатый фасованный', unit: '500 г', price: 54.99, rating: 4.91 },
    { id: 'onion-red', name: 'Лук красный', unit: '500 г', price: 99.99, rating: 4.88, markdown: true, originalPrice: 149.99 },
  ],
  basil: [
    { id: 'basil-pot', name: 'Базилик зелёный в горшочке', unit: '1 шт.', price: 119.99, rating: 4.9 },
    { id: 'basil-pack', name: 'Базилик свежий', unit: '30 г', price: 89.99, rating: 4.84 },
    { id: 'basil-dry', name: 'Базилик сушёный', unit: '10 г', price: 49.99, rating: 4.76 },
    { id: 'basil-markdown', name: 'Базилик свежий, срок сегодня', unit: '30 г', price: 44.99, rating: 4.8, markdown: true, originalPrice: 89.99 },
  ],
};

/**
 * Уценённые товары идут первыми внутри общего пула — так задан продуктовый
 * сценарий. Порядок внутри групп сохраняется. Настоящее ранжирование придёт
 * из модели: здесь только раскладка на две группы.
 */
export function markdownFirst(products: readonly CatalogProduct[]): CatalogProduct[] {
  return [
    ...products.filter((product) => product.markdown),
    ...products.filter((product) => !product.markdown),
  ];
}

export function productsForIngredient(ingredient: DemoIngredient): CatalogProduct[] {
  if (ingredient.id === 'pasta') return catalogProducts;
  return alternativeCatalogs[ingredient.id] ?? [
    { id: `${ingredient.id}-x5`, name: `${ingredient.name} X5`, unit: ingredient.amount, price: 99.99, rating: 4.9 },
    { id: `${ingredient.id}-choice`, name: `${ingredient.name} Отбор`, unit: ingredient.amount, price: 129.99, rating: 4.86 },
    { id: `${ingredient.id}-value`, name: `${ingredient.name} выгодно`, unit: ingredient.amount, price: 79.99, rating: 4.74 },
    { id: `${ingredient.id}-markdown`, name: `${ingredient.name}, короткий срок`, unit: ingredient.amount, price: 59.99, rating: 4.7, markdown: true, originalPrice: 99.99 },
  ];
}

export function formatPrice(price: number): { rubles: string; kopecks: string } {
  const [rubles, kopecks = '00'] = price.toFixed(2).split('.');
  return { rubles, kopecks };
}
