{% set drop_cols = ['customer_email', 'customer_password', 'product_image'] %}
{% set ts_cols = ['order_date_dateorders', 'shipping_date_dateorders'] %}
{% set money_cols = ['benefit_per_order', 'sales_per_customer', 'order_item_discount', 'order_item_product_price', 'sales', 'order_item_total', 'order_profit_per_order', 'product_price'] %}
{% set cols = adapter.get_columns_in_relation(source('dataco_raw', 'supply_chain_orders')) %}
{% set keep = [] %}

{% for col in cols %}
    {% set clean = col.name | lower | replace(' ', '_') | replace('(', '') | replace(')', '') %}
    {% if clean not in drop_cols %}
        {% do keep.append((col.name, clean)) %}
    {% endif %}
{% endfor %}

select
{% for original, clean in keep %}
    {% if clean in ts_cols %}
    try_to_timestamp("{{ original }}", 'MM/DD/YYYY HH24:MI') as {{ clean }}
    {% elif clean in money_cols %}
    cast("{{ original }}" as number(18, 2)) as {{ clean }}
    {% else %}
    "{{ original }}" as {{ clean }}
    {% endif %}{{ "," if not loop.last }}
{% endfor %}
from {{ source('dataco_raw', 'supply_chain_orders') }}