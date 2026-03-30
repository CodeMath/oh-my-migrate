# ── snapshot: 현재 상태를 에이전트 친화적으로 ──

$ agent-migrate snapshot
🔍 Scanning... (0.05s)

Models (SQLAlchemy):
  @m1 [model] User      (id, email, name, created_at)
  @m2 [model] Order     (id, user_id→@m1, total, status:Enum, created_at)
  @m3 [model] Product   (id, name, price, description)

Database (PostgreSQL):
  @d1 [table] users     (id, email, name, created_at)
  @d2 [table] orders    (id, user_id→@d1, total, status:varchar, created_at)
  @d3 [table] products  (id, name, price)

Drift:
  @m3 vs @d3: +description (model has, DB missing)
  @m2.status: Enum in model, varchar in DB

Migrations:
  @v1 001_initial           ✅ applied
  @v2 002_add_orders        ✅ applied
  @v3 003_add_products      ✅ applied
  (no pending migrations)

⚠️ 2 drifts detected — model and DB are out of sync


# ── diff: 구체적으로 뭐가 다른지 ──

$ agent-migrate diff
@m3 vs @d3 (Product):
  + description: Text (nullable)    ← model has, DB missing

@m2 vs @d2 (Order):
  ~ status: Enum('pending','paid','shipped') ← model
            varchar(255)                     ← DB
  ⚠️ This requires data migration (existing rows need mapping)


# ── plan: 마이그레이션 계획 (실행 전 프리뷰) ──

$ agent-migrate plan
📋 Migration Plan:

Step 1: ALTER TABLE products ADD COLUMN description TEXT;
Step 2: ALTER TABLE orders ALTER COLUMN status TYPE orderstatus
        USING status::orderstatus;
        (requires: CREATE TYPE orderstatus AS ENUM(...))

⚠️ Step 2 is destructive — existing varchar values must map to enum.
   Current values in DB: ['pending', 'paid', 'shipped', 'cancelled']
   Model enum: ['pending', 'paid', 'shipped']
   ❌ 'cancelled' exists in DB but NOT in model enum — will fail!

Risk: MEDIUM
Data loss: Step 2 may fail (23 rows with status='cancelled')

💡 Recommendation: Add 'cancelled' to model enum, or migrate data first.


# ── generate: Alembic 마이그레이션 파일 생성 ──

$ agent-migrate generate -m "add product description"
📄 Generated: alembic/versions/004_add_product_description.py

  def upgrade():
      op.add_column('products', sa.Column('description', sa.Text(), nullable=True))

  def downgrade():
      op.drop_column('products', 'description')

✅ Safe migration (additive only, no data loss risk)


# ── apply: 적용 (dry-run 기본) ──

$ agent-migrate apply
🏃 Dry-run mode (add --execute to actually apply)

Would execute:
  004_add_product_description.py

  ALTER TABLE products ADD COLUMN description TEXT;

Estimated impact: 0 data changes, 89 rows in products table unaffected.

$ agent-migrate apply --execute
✅ Migration 004 applied successfully (0.02s)


# ── guard: CI/CD 훅 ──

$ agent-migrate guard
🛡️ Pre-deploy check:

✅ No unapplied migrations
✅ Model and DB are in sync
✅ No destructive operations pending
✅ Safe to deploy
