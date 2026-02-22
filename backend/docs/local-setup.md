# Queryon Backend – Yerel Kurulum (macOS)

CLI ve backend’in çalışması için **PostgreSQL** ve **Qdrant** gerekir.

---

## 1. Homebrew ile kurulacaklar

```bash
# PostgreSQL (veritabanı)
brew install postgresql@16

# Qdrant Homebrew’da yok; Docker ile çalıştırılır
brew install --cask docker
```

(Docker yerine sadece Qdrant binary kullanmak istersen: [Qdrant – Installation](https://qdrant.tech/documentation/guides/installation/).)

---

## 2. Servisleri başlatma

### PostgreSQL

```bash
# Servisi başlat (macOS’ta arka planda çalışır)
brew services start postgresql@16

# İlk kez kullanıyorsan: “queryon” veritabanını oluştur
createdb queryon
# veya psql ile:
# psql postgres -c "CREATE DATABASE queryon;"
```

Bağlantı URL’i (varsayılan):

```bash
export DATABASE_URL="postgresql://localhost/queryon"
# Kullanıcı/şifre kullanan yerelde:
# export DATABASE_URL="postgresql://KULLANICI:SIFRE@localhost/queryon"
```

### Qdrant (Docker)

Docker Desktop’ı açtıktan sonra:

```bash
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

Varsayılan adres:

```bash
export QDRANT_URL="http://localhost:6333"
```

Durdurmak / silmek:

```bash
docker stop qdrant
docker rm qdrant
```

---

## 3. Ortam değişkenleri (özet)

Proje kökünde veya `backend` dizininde:

```bash
export DATABASE_URL="postgresql://localhost/queryon"
export QDRANT_URL="http://localhost:6333"
# İsteğe bağlı:
# export QDRANT_VECTOR_SIZE=1536
# export OPENAI_API_KEY="sk-..."
# export GEMINI_API_KEY="..."
```

`.env` kullanıyorsan bu değişkenleri oraya yazıp `source .env` veya `dotenv` ile yükleyebilirsin.

---

## 4. Kontrol

```bash
# PostgreSQL
psql "$DATABASE_URL" -c "SELECT 1;"

# Qdrant
curl -s http://localhost:6333/health
```

---

## 5. CLI’yı çalıştırma

```bash
cd /path/to/Queryon
source .venv/bin/activate
pip install -r backend/requirements.txt   # gerekirse
python -m backend.scripts.rag_cli
```

PostgreSQL ve Qdrant çalışıyorsa menü açılır; LLM/Embedding eklemek için ilgili API anahtarlarını (OPENAI / GEMINI) env’de tanımlaman yeterli.
