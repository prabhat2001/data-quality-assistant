"""Load a small, intentionally imperfect dataset so the assistant can be tried locally."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

SEED_SQL = """
CREATE TABLE public.customers (
    id integer PRIMARY KEY,
    full_name text,
    email text,
    country text,
    age integer,
    signed_up_on date
);

INSERT INTO public.customers (id, full_name, email, country, age, signed_up_on) VALUES
    (1, 'Ada Lovelace', 'ada@example.com', 'UK', 36, '2024-01-12'),
    (2, 'Grace Hopper', 'grace@navy.mil', 'US', 45, '2024-02-02'),
    (3, 'Alan Turing', 'alan@bletchley.uk', 'UK', 41, '2023-11-03'),
    (4, 'Katherine Johnson', 'katherine@nasa.gov', 'US', 58, '2023-08-19'),
    (5, 'Radia Perlman', 'radia@example.com', 'US', 52, '2024-03-01'),
    (6, 'Tim Berners-Lee', 'tim@w3.org', 'UK', 48, '2024-04-11'),
    (7, 'Margaret Hamilton', 'margaret@mit.edu', 'US', 55, '2023-12-12'),
    (8, 'Edsger Dijkstra', 'edsger@tue.nl', 'NL', 62, '2024-01-30'),
    (9, 'Barbara Liskov', 'barbara@mit.edu', 'US', 60, '2024-05-02'),
    (10, 'Donald Knuth', 'knuth@stanford.edu', 'US', 70, '2023-09-09'),
    (11, 'Linus Torvalds', 'linus@kernel.org', 'FI', 54, '2024-06-18'),
    (12, 'Guido van Rossum', 'guido@python.org', 'US', 67, '2024-02-28'),
    (13, 'Ada Lovelace Jr', 'ada@example.com', 'US', 29, '2024-07-01'),
    (14, 'No Email', NULL, 'US', 33, '2024-07-02'),
    (15, 'Bad Email', 'nope', 'US', 40, '2024-07-03'),
    (16, 'Mystery Country', 'mystery@example.com', '??', 27, '2024-07-04'),
    (17, 'Negative Age', 'young@example.com', 'IN', -3, '2024-07-05'),
    (18, 'Ancient Age', 'ancient@example.com', 'IN', 240, '2024-07-06'),
    (19, NULL, 'nameless@example.com', 'DE', NULL, '2024-07-07'),
    (20, 'Marie Curie', 'marie@example.com', 'FR', 31, '2024-07-08');

CREATE TABLE public.orders (
    id integer PRIMARY KEY,
    customer_id integer,
    status text,
    amount numeric(10, 2),
    ordered_on date
);

INSERT INTO public.orders (id, customer_id, status, amount, ordered_on) VALUES
    (1, 1, 'paid', 120.00, '2024-08-01'),
    (2, 2, 'pending', 45.50, '2024-08-02'),
    (3, 3, 'shipped', 300.00, '2024-08-03'),
    (4, 4, 'cancelled', 15.00, '2024-08-04'),
    (5, 5, 'paid', 88.25, '2024-08-05'),
    (6, 6, 'shipped', 240.00, '2024-08-06'),
    (7, 7, 'paid', 60.00, '2024-08-07'),
    (8, 8, 'pending', 12.00, '2024-08-08'),
    (9, 9999, 'paid', 50.00, '2024-08-09'),
    (10, 9, '??', 70.00, '2024-08-10'),
    (11, 10, 'paid', NULL, '2024-08-11'),
    (12, 11, 'paid', -20.00, '2024-08-12'),
    (13, 12, 'pending', 18.00, NULL),
    (14, 1, 'shipped', 500.00, '2024-08-13'),
    (15, 2, 'paid', 22.00, '2024-08-14'),
    (16, 3, NULL, 10.00, '2024-08-15');

CREATE TABLE public.products (
    sku text,
    name text,
    category text,
    price numeric(10, 2)
);

INSERT INTO public.products (sku, name, category, price) VALUES
    ('SKU-1', 'Keyboard', 'Electronics', 79.00),
    ('SKU-2', 'Mouse', 'Electronics', 25.00),
    ('SKU-3', 'Desk', 'Home', 220.00),
    ('SKU-4', 'Lamp', 'Home', 40.00),
    ('SKU-5', 'Coffee', 'Grocery', 12.50),
    ('SKU-1', 'Keyboard', 'Electronics', 79.00),
    ('SKU-6', 'Mystery item', 'misc??', 15.00),
    ('SKU-7', 'Ghost cable', 'Electronics', NULL),
    ('SKU-8', 'Refunded lamp', 'Home', -9.99),
    ('SKU-9', NULL, 'Grocery', 8.00),
    ('SKU-10', 'Cable', 'Electronics', 11.00);

ANALYZE public.customers;
ANALYZE public.orders;
ANALYZE public.products;
"""


def seed_if_needed(session: Session) -> bool:
    exists = session.execute(
        text(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'customers'
            """
        )
    ).first()
    if exists:
        return False
    for statement in SEED_SQL.split(";"):
        sql = statement.strip()
        if sql:
            session.execute(text(sql))
    session.commit()
    return True
