# Desarrollo

## Configuracion local

Este microservicio usa dos flujos de entorno:

- Django directo lee `flowkron-auth-service/.env` porque `config/settings/base.py` carga ese archivo con `django-environ`.
- Docker Compose local lee `flowkron-auth-service/.env.local` porque `docker-compose.yml` lo declara como `env_file`.

La plantilla versionable es `.env.example`; copia sus claves al archivo que corresponda y reemplaza los placeholders antes de levantar Django o Compose.


## Requisitos

- Python 3.13 recomendado
- PostgreSQL
- Redis
- Docker opcional

## Setup local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts/generate_jwt_keys.py
python manage.py migrate
python manage.py seed_iam
python manage.py seed_iam_advanced
python manage.py runserver
```

## Settings

Por defecto:

```text
DJANGO_SETTINGS_MODULE=config.settings.base
```

Produccion:

```text
DJANGO_SETTINGS_MODULE=config.settings.base
```

## Convenciones de codigo

- Mantener apps por dominio.
- Views solo coordinan HTTP.
- Serializers validan input/output.
- Services contienen reglas de negocio.
- Models representan persistencia e invariantes simples.
- Permisos DRF viven en `apps/shared/permissions.py`.
- Errores deben pasar por el handler estandar.
- Operaciones sensibles deben auditarse.

## Flujo para agregar endpoint

1. Definir modelo o servicio si aplica.
2. Crear serializer de input/output.
3. Crear view o viewset.
4. Agregar ruta.
5. Agregar permisos DRF.
6. Registrar auditoria si es sensible.
7. Agregar tests.
8. Actualizar docs.
9. Validar OpenAPI.

## Flujo para agregar modelo

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py test
```

Reglas:

- declarar `db_table` con prefijo `iam_`
- agregar indices para consultas frecuentes
- definir constraints para unicidad
- no guardar secretos en claro

## Flujo para cambios de seguridad

Todo cambio de seguridad debe responder:

- Que amenaza mitiga?
- Que evento de auditoria genera?
- Que pruebas lo cubren?
- Que pasa si falla parcialmente?
- Como se revoca o revierte?
- Como se monitorea?

## Calidad minima antes de merge

```powershell
python -m compileall -q apps config scripts manage.py
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
docker compose config
```

Si cambia Docker:

```powershell
docker compose build app
```

Para probar el Compose local del repositorio usa `.env.local`:

```powershell
Copy-Item .env.example .env.local
docker compose --env-file .env.local config
docker compose --env-file .env.local up --build
```

## No hacer

- No usar tenant recibido desde frontend sin validar membership.
- No registrar tokens completos en logs.
- No guardar API keys en claro.
- No devolver client secrets salvo en creacion controlada.
- No mezclar logica de negocio compleja en views.
- No crear permisos implicitos sin seed/documentacion.
