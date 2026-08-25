-- 태웅 DB 확인용. 실행: docker exec -i pg psql -U kiosk -d kiosk < db/check.sql
\echo '== menu_items (B001~B003 기대) =='
SELECT menu_id, name, aliases, single_price, set_price, active FROM menu_items ORDER BY menu_id;

\echo '== knowledge_documents (seed 5건 기대) =='
SELECT document_id, menu_id, document_type, content FROM knowledge_documents ORDER BY document_id;

\echo '== 최근 주문 10건 (workflow/agent 둘 다 저장되는지) =='
SELECT o.order_number, o.execution_mode, o.total_price, o.status, o.created_at,
       i.menu_id, i.order_option, i.quantity, i.unit_price, i.line_total
FROM orders o
LEFT JOIN order_items i ON i.order_id = o.order_id
ORDER BY o.order_id DESC, i.order_item_id
LIMIT 10;

\echo '== 실행 방식별 주문 수 =='
SELECT execution_mode, count(*) AS orders, coalesce(sum(total_price),0) AS total
FROM orders GROUP BY execution_mode ORDER BY execution_mode;
