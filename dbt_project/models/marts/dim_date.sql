with bounds as (
    select
        min(order_date_dateorders)::date as first_day,
        max(shipping_date_dateorders)::date as last_day
    from {{ ref('stg_supply_chain_orders') }}
),

spine as (
    select
        dateadd(day, seq4(), b.first_day) as date_day,
        b.last_day
    from bounds as b
    cross join table(generator(rowcount => 5000))
)

select
    to_number(to_char(date_day, 'YYYYMMDD')) as date_key,
    date_day,
    year(date_day) as calendar_year,
    quarter(date_day) as calendar_quarter,
    month(date_day) as calendar_month,
    monthname(date_day) as month_name,
    to_char(date_day, 'YYYY-MM') as year_month,
    dayname(date_day) as day_name,
    dayname(date_day) in ('Sat', 'Sun') as is_weekend
from spine
where date_day <= last_day
