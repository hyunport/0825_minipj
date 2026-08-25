INSERT INTO menu_items (
    menu_id, name, aliases, description, single_price, set_price, active
) VALUES
    ('B001', '불고기버거', '불고기,불고기 버거', '달콤한 불고기 소스가 들어간 햄버거', 5000, 7500, TRUE),
    ('B002', '치즈버거', '치즈,치즈 버거', '고소한 치즈가 들어간 햄버거', 5500, 8000, TRUE),
    ('B003', '새우버거', '새우,새우 버거', '바삭한 새우 패티가 들어간 햄버거', 6000, 8500, TRUE)
ON CONFLICT (menu_id) DO UPDATE SET
    name = EXCLUDED.name,
    aliases = EXCLUDED.aliases,
    description = EXCLUDED.description,
    single_price = EXCLUDED.single_price,
    set_price = EXCLUDED.set_price,
    active = EXCLUDED.active,
    updated_at = NOW();

INSERT INTO knowledge_documents (menu_id, document_type, content)
SELECT seed.menu_id, seed.document_type, seed.content
FROM (
    VALUES
        ('B001', 'menu', '불고기, 불고기 버거는 불고기버거를 뜻합니다. 달콤한 불고기 소스가 특징입니다.'),
        ('B002', 'menu', '치즈, 치즈 버거는 치즈버거를 뜻합니다. 고소한 치즈가 들어갑니다.'),
        ('B003', 'menu', '새우, 새우 버거는 새우버거를 뜻합니다. 바삭한 새우 패티가 들어갑니다.'),
        (NULL, 'policy', '주문에는 메뉴, 단품 또는 세트, 수량이 필요합니다.'),
        (NULL, 'policy', '세트는 버거, 감자튀김, 콜라로 구성됩니다.')
) AS seed(menu_id, document_type, content)
WHERE NOT EXISTS (
    SELECT 1
    FROM knowledge_documents existing
    WHERE existing.document_type = seed.document_type
      AND existing.content = seed.content
);
