select distinct
    md5(shipping_mode) as shipping_mode_key,
    shipping_mode
from {{ ref('stg_supply_chain_orders') }}
