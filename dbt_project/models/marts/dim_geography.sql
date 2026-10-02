select distinct
    md5(concat_ws('|', order_city, order_state, order_country, order_region, market)) as geography_key,
    order_city as city,
    order_state as state,
    order_country as country,
    order_region as region,
    market
from {{ ref('stg_supply_chain_orders') }}
