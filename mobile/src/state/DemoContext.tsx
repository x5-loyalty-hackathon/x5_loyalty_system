import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { getProgress, getRecommendations, submitReceipt } from '../api/endpoints';
import type { ProgressSnapshot, RecipeRecommendation } from '../api/types';
import { demoRecipes, type CatalogProduct, type DemoIngredient, type DemoRecipe } from '../data/demo';

type RecipesStatus = 'idle' | 'loading' | 'live' | 'mock';
type AsyncStatus = 'idle' | 'loading' | 'ready' | 'error';

interface DemoValue {
  recipes: DemoRecipe[];
  recipesStatus: RecipesStatus;
  recipesError: string | null;
  loadRecipes: () => Promise<void>;
  selectedRecipe: DemoRecipe;
  selectRecipe: (recipeId: string) => void;
  selectedIngredient: DemoIngredient;
  selectIngredient: (ingredientId: string) => void;
  isIngredientAvailable: (ingredient: DemoIngredient) => boolean;
  toggleIngredient: (ingredient: DemoIngredient) => void;
  basket: CatalogProduct[];
  addToBasket: (product: CatalogProduct) => void;

  progress: ProgressSnapshot | null;
  progressStatus: AsyncStatus;
  progressError: string | null;
  loadProgress: () => Promise<void>;

  /** Отправляет чек и обновляет прогресс. Возвращает статус события от backend. */
  confirmPurchase: () => Promise<string | null>;
  purchaseStatus: AsyncStatus;
  purchaseError: string | null;
  receiptStatus: string | null;
}

const DemoCtx = createContext<DemoValue | null>(null);

function mergeRecommendation(recipe: RecipeRecommendation): DemoRecipe {
  const local = demoRecipes.find((item) => item.id === recipe.recipe_id);
  return {
    id: recipe.recipe_id,
    title: recipe.title,
    mode: recipe.mode,
    time: local?.time ?? 30,
    servings: local?.servings ?? 2,
    description: local?.description ?? 'Рецепт подобран по продуктам из последних чеков.',
    ingredients: recipe.ingredients.map((item) => {
      const localIngredient = local?.ingredients.find((candidate) => candidate.id === item.ingredient_id);
      return {
        id: item.ingredient_id,
        name: item.name,
        category: item.category,
        amount: localIngredient?.amount ?? 'по вкусу',
        emoji: localIngredient?.emoji ?? '•',
        defaultAvailable: item.source === 'receipt' || item.source === 'home',
      };
    }),
    steps: local?.steps ?? [
      { title: 'Подготовить ингредиенты', minutes: 10 },
      { title: 'Приготовить блюдо', minutes: 20 },
    ],
    lastCooked: local?.lastCooked,
    note: local?.note,
  };
}

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const [recipes, setRecipes] = useState<DemoRecipe[]>(demoRecipes);
  const [recipesStatus, setRecipesStatus] = useState<RecipesStatus>('idle');
  const [recipesError, setRecipesError] = useState<string | null>(null);
  const [selectedRecipeId, setSelectedRecipeId] = useState(demoRecipes[0].id);
  const [selectedIngredientId, setSelectedIngredientId] = useState(demoRecipes[0].ingredients[0].id);
  const [ingredientOverrides, setIngredientOverrides] = useState<Record<string, boolean>>({});
  const [basket, setBasket] = useState<CatalogProduct[]>([]);
  const [progress, setProgress] = useState<ProgressSnapshot | null>(null);
  const [progressStatus, setProgressStatus] = useState<AsyncStatus>('idle');
  const [progressError, setProgressError] = useState<string | null>(null);
  const [purchaseStatus, setPurchaseStatus] = useState<AsyncStatus>('idle');
  const [purchaseError, setPurchaseError] = useState<string | null>(null);
  const [receiptStatus, setReceiptStatus] = useState<string | null>(null);

  const loadProgress = useCallback(async () => {
    setProgressStatus('loading');
    setProgressError(null);
    try {
      setProgress(await getProgress());
      setProgressStatus('ready');
    } catch (error) {
      setProgressError((error as Error).message);
      setProgressStatus('error');
    }
  }, []);

  const loadRecipes = useCallback(async () => {
    setRecipesStatus('loading');
    setRecipesError(null);
    try {
      const response = await getRecommendations();
      const liveRecipes = response.recommendations.map(mergeRecommendation);
      const liveIds = new Set(liveRecipes.map((recipe) => recipe.id));
      setRecipes([...liveRecipes, ...demoRecipes.filter((recipe) => !liveIds.has(recipe.id))]);
      setRecipesStatus('live');
    } catch (error) {
      setRecipes(demoRecipes);
      setRecipesError((error as Error).message);
      setRecipesStatus('mock');
    }
  }, []);

  const selectedRecipe = recipes.find((recipe) => recipe.id === selectedRecipeId) ?? recipes[0] ?? demoRecipes[0];
  const selectedIngredient = selectedRecipe.ingredients.find((item) => item.id === selectedIngredientId) ?? selectedRecipe.ingredients[0];

  const confirmPurchase = useCallback(async () => {
    setPurchaseStatus('loading');
    setPurchaseError(null);
    try {
      // Ответ на чек уже несёт progress; отдельный GET подтверждает, что
      // состояние действительно сохранилось на backend.
      const receipt = await submitReceipt(selectedRecipeId);
      setReceiptStatus(receipt.status);
      setProgress(receipt.progress);
      setProgressStatus('ready');
      await loadProgress();
      setPurchaseStatus('ready');
      return receipt.status as string;
    } catch (error) {
      setPurchaseError((error as Error).message);
      setPurchaseStatus('error');
      return null;
    }
  }, [loadProgress, selectedRecipeId]);

  const value = useMemo<DemoValue>(() => ({
    recipes,
    recipesStatus,
    recipesError,
    loadRecipes,
    selectedRecipe,
    selectRecipe: (recipeId: string) => {
      setSelectedRecipeId(recipeId);
      const recipe = recipes.find((item) => item.id === recipeId);
      if (recipe?.ingredients[0]) setSelectedIngredientId(recipe.ingredients[0].id);
    },
    selectedIngredient,
    selectIngredient: setSelectedIngredientId,
    isIngredientAvailable: (ingredient: DemoIngredient) =>
      ingredientOverrides[ingredient.id] ?? ingredient.defaultAvailable,
    toggleIngredient: (ingredient: DemoIngredient) => setIngredientOverrides((current) => ({
      ...current,
      [ingredient.id]: !(current[ingredient.id] ?? ingredient.defaultAvailable),
    })),
    basket,
    addToBasket: (product: CatalogProduct) => setBasket((current) => [...current, product]),
    progress,
    progressStatus,
    progressError,
    loadProgress,
    confirmPurchase,
    purchaseStatus,
    purchaseError,
    receiptStatus,
  }), [
    basket, confirmPurchase, ingredientOverrides, loadProgress, loadRecipes, progress,
    progressError, progressStatus, purchaseError, purchaseStatus, receiptStatus,
    recipes, recipesError, recipesStatus, selectedIngredient, selectedRecipe,
  ]);

  return <DemoCtx.Provider value={value}>{children}</DemoCtx.Provider>;
}

export function useDemo(): DemoValue {
  const value = useContext(DemoCtx);
  if (!value) throw new Error('useDemo вне DemoProvider');
  return value;
}
