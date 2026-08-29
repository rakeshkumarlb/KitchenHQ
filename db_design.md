 # KitchenHQ database schema

Use this schema when answering questions about KitchenHQ. Query the relevant table before making claims about stored data. The database currently contains no sample rows.

## Tables

### `inventory`
Tracks available ingredients and stock thresholds.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Ingredient identifier |
| `item_name` | TEXT | Ingredient name |
| `category` | TEXT | Ingredient category |
| `quantity` | REAL | Quantity currently available |
| `unit` | TEXT | Unit of measurement |
| `minimum_threshold` | REAL | Reorder threshold |
| `last_updated` | DATETIME DEFAULT CURRENT_TIMESTAMP | Last stock update |

### `meal_feedback`
Stores feedback and child ratings for served dishes.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Feedback identifier |
| `date_served` | DATE | Date the dish was served |
| `dish_name` | TEXT | Dish name |
| `kid_rating` | INTEGER | Child rating |
| `human_feedback` | TEXT | Additional feedback |

### `prep_schedule`
Defines recurring food-preparation tasks.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Schedule identifier |
| `trigger_day` | TEXT | Day on which the task runs |
| `trigger_time` | TEXT | Time at which the task runs |
| `task_type` | TEXT | Task category |
| `instructions` | TEXT | Preparation instructions |

### `task_acknowledgement`
Tracks whether scheduled tasks were completed.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Task identifier |
| `task_date` | DATE | Date of the task |
| `task_type` | TEXT | Task category |
| `task_description` | TEXT | Task details |
| `is_completed` | BOOLEAN DEFAULT 0 | Completion status |
| `human_notes` | TEXT | Notes about the task |

### `wastage_log`
Records discarded ingredients.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Wastage record identifier |
| `item_name` | TEXT | Discarded ingredient |
| `quantity_wasted` | REAL | Amount discarded |
| `date_logged` | DATETIME DEFAULT CURRENT_TIMESTAMP | Time recorded |

### `weekly_menu`
Stores planned meals for each day of the week.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | Menu item identifier |
| `day_of_week` | TEXT | Planned day |
| `meal_type` | TEXT | Meal category, such as breakfast or dinner |
| `dish_name` | TEXT | Dish name |
| `is_kid_friendly` | BOOLEAN | Whether the dish is kid-friendly |
| `macros` | TEXT | Macronutrient information |
| `ingredients` | TEXT | Ingredients for the dish |

## SQL definition

```sql
CREATE TABLE inventory (id INTEGER PRIMARY KEY, item_name TEXT, category TEXT, quantity REAL, unit TEXT, minimum_threshold REAL, last_updated DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE meal_feedback (id INTEGER PRIMARY KEY, date_served DATE, dish_name TEXT, kid_rating INTEGER, human_feedback TEXT);
CREATE TABLE prep_schedule (id INTEGER PRIMARY KEY, trigger_day TEXT, trigger_time TEXT, task_type TEXT, instructions TEXT);
CREATE TABLE task_acknowledgement (id INTEGER PRIMARY KEY, task_date DATE, task_type TEXT, task_description TEXT, is_completed BOOLEAN DEFAULT 0, human_notes TEXT);
CREATE TABLE wastage_log (id INTEGER PRIMARY KEY, item_name TEXT, quantity_wasted REAL, date_logged DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE weekly_menu (id INTEGER PRIMARY KEY, day_of_week TEXT, meal_type TEXT, dish_name TEXT, is_kid_friendly BOOLEAN, macros TEXT, ingredients TEXT);
```