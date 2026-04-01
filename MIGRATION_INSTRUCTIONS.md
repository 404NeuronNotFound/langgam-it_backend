# Migration Instructions

## Required Action

The database migrations have been created but not yet applied. You need to run the following command in your terminal with the virtual environment activated:

```bash
# Activate virtual environment (if not already activated)
venv\Scripts\activate

# Run migrations
python manage.py migrate
```

This will create the following new tables:
- `api_investment` - Individual investment records
- `api_monthsummary` - End-of-month financial summaries
- `api_investmentallocation` - Investment allocation tracking

## What Changed

### New Features Added

1. **Investment Management**
   - Create, read, update, delete individual investments
   - Track investment type, amount invested, and current value
   - Automatic profit/loss calculation

2. **Investment Allocation Validation**
   - Prevents adding investments beyond the allocated total
   - Users must transfer funds from savings to increase investment budget
   - Clear error messages guide users on available investment budget

3. **End-of-Month Summaries**
   - Automatic snapshots of monthly financial activity
   - Tracks income, expenses, savings, and net worth changes

4. **Investment Allocation Tracking**
   - Ensures sum of all investments equals the allocated budget
   - Automatic syncing when investments are added/updated/deleted
   - Validation to catch allocation mismatches

### API Endpoints

**Investment Management:**
- `GET /api/investments/` - List all investments
- `POST /api/investments/` - Create new investment (with validation)
- `GET /api/investments/<id>/` - Get specific investment
- `PATCH /api/investments/<id>/` - Update investment
- `DELETE /api/investments/<id>/` - Delete investment

**Investment Allocation:**
- `GET /api/investments/allocation/` - Get allocation summary
- `PATCH /api/investments/allocation/` - Update allocated total

**Reports:**
- `GET /api/reports/` - Get monthly summaries and charts

**Month Management:**
- `POST /api/month/close/` - Close current month and create summary

## Investment Workflow

1. **Setup Wizard** - User enters total investment amount (e.g., ₱120,000)
   - This sets `InvestmentAllocation.total_allocated = 120000`

2. **Add Investments** - User adds individual investments
   - Each investment's `total_invested` is validated against allocated total
   - Sum of all `total_invested` must equal `total_allocated`
   - Example:
     - BDO Stock: ₱40,000
     - Bitcoin: ₱50,000
     - Real Estate: ₱30,000
     - Total: ₱120,000 ✓

3. **Transfer Funds** - If user wants to add more investments
   - User transfers funds from savings to investments via `/api/divest/`
   - This increases `InvestmentAllocation.total_allocated`
   - Now user can add more investments up to the new total

4. **Track Performance** - Monitor profit/loss
   - Update `current_value` as market prices change
   - System automatically calculates `profit_loss = current_value - total_invested`
   - View allocation summary at `/api/investments/allocation/`

## Database Schema

### Investment Model
```
- id (PK)
- user (FK to User)
- name (CharField)
- type (CharField: stocks, crypto, bonds, mutual_funds, real_estate, other)
- total_invested (DecimalField)
- current_value (DecimalField)
- created_at (DateTimeField)
- updated_at (DateTimeField)
```

### InvestmentAllocation Model
```
- id (PK)
- user (OneToOneField to User)
- total_allocated (DecimalField) - from setup wizard
- total_current_value (DecimalField) - computed from investments
- total_profit_loss (DecimalField) - computed
- updated_at (DateTimeField)
```

### MonthSummary Model
```
- id (PK)
- user (FK to User)
- cycle (OneToOneField to MonthCycle)
- total_income (DecimalField)
- total_expenses (DecimalField)
- total_saved (DecimalField)
- remaining_carried_over (DecimalField)
- net_worth_start (DecimalField)
- net_worth_end (DecimalField)
- created_at (DateTimeField)
```

## Validation Rules

### Investment Creation
- `total_invested` must be positive
- Sum of all investments' `total_invested` ≤ `InvestmentAllocation.total_allocated`
- Error message shows available budget and suggests transferring funds

### Investment Update
- Same validation as creation
- Prevents exceeding allocated total

### Investment Deletion
- Automatically syncs `investments_total` in FinancialProfile
- Frees up allocation space for new investments

## Testing the Features

After running migrations, test with:

```bash
# 1. Get current profile
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/finance/profile/

# 2. Get investment allocation
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/investments/allocation/

# 3. Create an investment (will fail if exceeds allocated total)
curl -X POST -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"BDO Stock","type":"stocks","total_invested":"50000","current_value":"55000"}' \
  http://localhost:8000/api/investments/

# 4. List investments
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/investments/

# 5. Get reports
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/reports/
```

## Troubleshooting

**Error: "no such table: api_investmentallocation"**
- Solution: Run `python manage.py migrate`

**Error: "Cannot add investment. Total invested would exceed allocated budget"**
- Solution: Transfer funds from savings using `/api/divest/` endpoint
- Or update allocation using `PATCH /api/investments/allocation/`

**Error: "Investment allocation mismatch"**
- Solution: Check that sum of all investments' `total_invested` equals `total_allocated`
- Use `/api/investments/allocation/` to see current state
