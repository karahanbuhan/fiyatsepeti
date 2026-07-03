
# Fiyat Sepeti

**Fiyat Sepeti**, günlük alışveriş kayıtlarını veritabanında saklayan, tek prompttan birden fazla ürünü ayrıştırabilen, Excel benzeri tablo sunan ve kişisel fiyat değişimi/enflasyon takibi yapan bir agent uygulamasıdır.

## Proje Başlığı

**Sepet Hafızası: Kişisel Alışveriş ve Fiyat Değişimi Takip Agent'ı**

## Amaç

Günlük market alışverişleri genellikle sistemli tutulmadığı için ürünlerin zaman içindeki fiyat değişimini görmek zorlaşır. Bu proje, kullanıcının alışveriş kayıtlarını düzenli biçimde saklar ve geçmiş fiyatlarla karşılaştırma yapar.

## Ekran Görüntüleri

<img width="1223" height="638" alt="Screenshot 2026-07-03 113303" src="https://github.com/user-attachments/assets/10728e63-67fa-4e13-aeb6-9b9edb5a276d" />
<img width="1224" height="514" alt="2" src="https://github.com/user-attachments/assets/d4ec6de4-2b23-4327-bab3-95d478bfa2ea" />
<img width="1217" height="627" alt="3" src="https://github.com/user-attachments/assets/b650cde4-04d7-4793-8bad-233b6942b153" />
<img width="1239" height="638" alt="4" src="https://github.com/user-attachments/assets/36c8f14c-b2f5-443c-b1c3-b760a6591f2f" />

## Kullanılan Teknolojiler

- Python
- Streamlit
- SQLite
- Pandas
- OpenPyXL

## Kurulum

Terminali proje klasöründe açıp şu komutları çalıştır:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Eğer Windows'ta `python` çalışmazsa:

```bash
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## Temel Özellikler

1. Tek prompt ile çoklu alışveriş kaydı alma
2. Doğal metinden ürün, miktar, birim, fiyat ve market bilgisi ayrıştırma
3. Manuel kayıt ekleme
4. SQLite veritabanında kayıt tutma
5. Excel/CSV dışa aktarma
6. Aylık toplam harcama grafiği
7. Günlük harcama grafiği
8. Kategoriye göre harcama grafiği
9. Markete göre harcama grafiği
10. En çok harcama yapılan ürünleri gösterme
11. Ürün bazlı fiyat değişimi/enflasyon oranı hesaplama

## Agent Giriş Örnekleri

Doğal metin:

```text
Bugün BIM'den 2 kg domates 130 TL, 1 lt süt 42 TL, 3 paket makarna 75 TL aldım
```

Daha güvenli yarı yapılandırılmış format:

```text
domates; 2026-05-20; 2; kg; 130; market=BIM; kategori=Gıda
süt; 2026-05-20; 1; lt; 42; market=A101; kategori=Gıda
makarna; 2026-05-20; 3; paket; 75; market=Migros; kategori=Gıda
```

## Enflasyon / Fiyat Değişimi Formülü

```text
Fiyat Değişim Oranı = ((Yeni Birim Fiyat - Eski Birim Fiyat) / Eski Birim Fiyat) * 100
```

Örnek:

```text
Eski süt fiyatı: 25 TL
Yeni süt fiyatı: 42 TL

((42 - 25) / 25) * 100 = %68
```

## Veritabanı

Tablo adı: `purchases`

| Alan | Açıklama |
|---|---|
| id | Otomatik kayıt numarası |
| purchase_date | Alışveriş tarihi |
| item_name | Ürün adı |
| category | Kategori |
| quantity | Miktar |
| unit | Birim |
| unit_price | Birim fiyat |
| total_price | Toplam fiyat |
| store | Market / mağaza |
| note | Orijinal not |
| created_at | Sisteme eklenme zamanı |

## Akademik Açıklama

Bu proje genel ülke enflasyonunu değil, kullanıcının kendi alışveriş verileri üzerinden **kişisel alışveriş sepeti bazlı fiyat değişimini** hesaplar. Bu nedenle sistemin çıktısı kişisel harcama takibi ve ürün bazlı fiyat karşılaştırmasıdır.

## Geliştirilebilir Yönler

- OCR ile fiş okuma
- Kullanıcı hesabı sistemi
- Gerçek enflasyon verileriyle karşılaştırma
- Daha gelişmiş doğal dil işleme modeli
- Otomatik aylık rapor üretimi
