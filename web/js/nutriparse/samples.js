/* ---------- samples ---------- */

const SAMPLE_MEAL = {
  items: [
    { name: 'Roti (whole wheat)', portion: '2 medium', calories: 224, protein: 7.4, carbs: 43.2, fat: 3.6 },
    { name: 'Dal (toor)', portion: '1 bowl (200 ml)', calories: 180, protein: 9.5, carbs: 26, fat: 4.2 },
    { name: 'Lassi (sweet)', portion: '1 glass (250 ml)', calories: 165, protein: 6.8, carbs: 21.5, fat: 5.9 },
  ],
  totals: { calories: 569, protein: 23.7, carbs: 90.7, fat: 13.7 },
  meta: { provider: 'sample', model: 'sample/fixture', elapsed_ms: 0, prompt_tokens: null, completion_tokens: null, sample: true },
};

const SAMPLE_RECIPES = {
  recipes: [
    {
      title: 'Rice & Egg Skillet of Questionable Confidence',
      description: 'A weekday rescue mission that tastes like you planned it.',
      ingredients_used: ['cooked rice', '2 eggs', 'half a bell pepper'],
      pantry_extras: ['oil', 'salt', 'soy sauce'],
      steps: [
        'Heat a wide pan with a little oil until it shimmers.',
        'Fry the pepper for two minutes, then add the rice and press it flat.',
        'Push everything aside, scramble the eggs in the gap, then fold together.',
        'Season, taste, and resist eating from the pan.',
      ],
      servings: 2,
      nutrition: { calories: 412, protein: 16.4, carbs: 48.2, fat: 15.1 },
      image_pending: false,
      image_unavailable: true,
    },
    {
      title: 'Spinach That Finally Gets Eaten',
      description: 'A green-heavy bowl for the spinach you bought with good intentions.',
      ingredients_used: ['spinach', 'cooked rice', '2 eggs'],
      pantry_extras: ['garlic', 'chilli flakes', 'lemon'],
      steps: [
        'Wilt the spinach in a hot pan with garlic.',
        'Fold through the rice and warm it back up.',
        'Top with a soft-boiled or fried egg.',
        'Finish with lemon and chilli flakes.',
      ],
      servings: 2,
      nutrition: { calories: 365, protein: 18.2, carbs: 39.8, fat: 13.4 },
      image_pending: false,
      image_unavailable: true,
    },
    {
      title: 'Bell Pepper Confetti Bowl',
      description: 'Crunchy, bright, and forgiving of whatever else is in the fridge.',
      ingredients_used: ['half a bell pepper', 'cooked rice', '2 eggs'],
      pantry_extras: ['yogurt', 'cumin', 'salt'],
      steps: [
        'Dice the pepper small enough that it disappears into the rice.',
        'Toast cumin in oil, add the pepper, and cook until soft.',
        'Stir in the rice, then fold in a spoon of yogurt off the heat.',
        'Top with a jammy egg and season aggressively.',
      ],
      servings: 2,
      nutrition: { calories: 388, protein: 17.1, carbs: 44.6, fat: 14.8 },
      image_pending: false,
      image_unavailable: true,
    },
  ],
  meta: { provider: 'sample', model: 'sample/fixture', elapsed_ms: 0, prompt_tokens: null, completion_tokens: null, sample: true },
};

function showSample(mode) {
  hideError();
  if (mode === 'cook') {
    state.cookReady = true;
    state.cookRecipes = SAMPLE_RECIPES.recipes;
    el.text.value = 'cooked rice, 2 eggs, half a bell pepper';
    renderRecipes(SAMPLE_RECIPES.recipes, SAMPLE_RECIPES.meta, SAMPLE_RECIPES);
    announce('Sample recipes loaded. Nothing was sent to the model.');
  } else {
    state.estimateReady = true;
    el.text.value = '2 rotis, dal, and a glass of lassi';
    renderItems(SAMPLE_MEAL.items, SAMPLE_MEAL.meta, SAMPLE_MEAL);
    announce('Sample result loaded. Nothing was sent to the model.');
  }
  updateCount();
  syncPanels();
}

