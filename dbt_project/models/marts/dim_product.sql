select
    product_card_id as product_key,
    product_name,
    product_category_id as category_id,
    category_name,
    department_id,
    department_name,
    product_price as list_price,
    product_status
from {{ ref('stg_supply_chain_orders') }}
qualify row_number() over (
    partition by product_card_id
    order by order_date_dateorders desc
) = 1
