/** Curated demo copy, not model-generated instructions. Ingredient keys must match. */
export const recipeDetails: Record<string, { ingredientIds: string[]; steps: string[] }> = {
  spaghetti_bolognese: {
    ingredientIds: ['pasta', 'mince', 'tomato', 'onion', 'cheese', 'basil'],
    steps: [
      'Подготовить продукты, измельчить лук и томаты.',
      'Обжарить лук, добавить фарш и разбить комочки.',
      'Добавить томаты и тушить соус до полной готовности фарша.',
      'Отварить спагетти по инструкции на упаковке, смешать с соусом.',
      'Добавить тёртый сыр. Базилик — по желанию.',
    ],
  },
  pasta_tomatoes: {
    ingredientIds: ['pasta', 'tomato', 'cheese'],
    steps: [
      'Подготовить и нарезать томаты.',
      'Отварить пасту по инструкции на упаковке.',
      'Прогреть томаты с небольшим количеством воды от пасты, смешать с готовой пастой.',
      'Добавить сыр по желанию.',
    ],
  },
  chicken_soup: {
    ingredientIds: ['chicken', 'carrot', 'onion'],
    steps: [
      'Подготовить овощи и курицу, использовать отдельную доску для сырого мяса.',
      'Положить курицу в воду, довести до кипения и варить до полной готовности.',
      'Добавить нарезанные морковь и лук, варить до готовности овощей.',
    ],
  },
};
