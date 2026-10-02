select
    customer_id as customer_key,
    customer_fname as first_name,
    customer_lname as last_name,
    customer_segment,
    customer_city,
    customer_state,
    customer_country,
    customer_zipcode
from {{ ref('stg_supply_chain_orders') }}
qualify row_number() over (
    partition by customer_id
    order by order_date_dateorders desc
) = 1
