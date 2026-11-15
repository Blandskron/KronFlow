---
applyTo: "**/{tests,test,__tests__}/**/*"
---

# Convenciones de Testing

- **Framework:** Usa el framework de pruebas nativo de Django (`django.test.TestCase`).
- **Nivel de Cobertura:** Cada cambio de lógica funcional debe contar con pruebas unitarias o de integración.
- **Aislamiento Multi-Tenant:** Diseña pruebas que verifiquen la prohibición de accesos cruzados entre tenants (*cross-tenant access*).
- **Mocks:**
  - Prefiere la base de datos temporal de pruebas antes que mocks de base de datos.
- **No Silenciar Fallos:** No borres ni dejes vacías pruebas con fallas. Repórtalas y corrígelas según el comportamiento esperado.
- **Comando de Ejecución:** Corre la suite completa local con:
  ```bash
  python manage.py test
  ```
