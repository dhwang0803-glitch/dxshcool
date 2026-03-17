"""정규화 단위 테스트."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from Shopping_Ad.src.normalizer import normalize


class TestNormalize:
    """normalize() 함수 테스트 케이스."""

    def test_remove_brackets(self):
        assert "샤인머스캣" in normalize("[방송최저가] 샤인머스캣 2kg")
        assert "홍삼정" in normalize("(특별구성) 홍삼정 선물세트")

    def test_remove_special_chars(self):
        result = normalize("●오늘만★특가● 프리미엄 견과류")
        assert "●" not in result
        assert "★" not in result
        assert "견과류" in result

    def test_remove_quantity(self):
        result = normalize("프리미엄 한우 갈비세트 1박스")
        assert "1박스" not in result
        assert "한우" in result

    def test_remove_quantity_grams(self):
        result = normalize("제주 감귤 500g 3박스")
        assert "500g" not in result
        assert "3박스" not in result

    def test_remove_promo_keywords(self):
        result = normalize("방송최저가 무료배송 프리미엄 이불 세트")
        assert "방송최저가" not in result
        assert "무료배송" not in result
        assert "이불" in result

    def test_remove_possessive(self):
        result = normalize("김박사의 프리미엄 홍삼")
        assert "박사" not in result
        assert "홍삼" in result

    def test_brand_prefix_removal(self):
        result = normalize("LG 스타일러 트롬")
        assert "스타일러" in result

    def test_multiple_spaces(self):
        result = normalize("프리미엄   고급   이불")
        assert "  " not in result

    def test_empty_string(self):
        assert normalize("") == ""
        assert normalize("   ") == ""

    def test_numbers_only(self):
        result = normalize("12345")
        assert result == "12345"

    def test_english_only(self):
        result = normalize("Premium Quality Silk")
        assert "Silk" in result

    def test_real_product_1(self):
        result = normalize("[긴급편성] ●삼성● 비스포크 냉장고 RF85A9103AP")
        assert "비스포크" in result
        assert "냉장고" in result
        assert "●" not in result

    def test_real_product_2(self):
        result = normalize("(1+1) 풀무원 국산콩 두부 300g 2팩 무료배송")
        assert "두부" in result
        assert "1+1" not in result
        assert "무료배송" not in result

    def test_real_product_3(self):
        result = normalize("★방송에서만★ 다이슨 에어랩 컴플리트 롱")
        assert "에어랩" in result
        assert "★" not in result
        assert "방송에서만" not in result

    def test_complex_product(self):
        result = normalize("[특별할인](추가증정) NIKE 에어맥스 90 🔥초특가🔥 2켤레")
        assert "에어맥스" in result
        assert "🔥" not in result
        assert "특별할인" not in result
        assert "2켤레" not in result
