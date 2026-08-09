from schemas.models import Course

def test_dynamic_course():
    print("Testing dynamic RDF schema generation...")
    
    # 1. Instantiate Course
    c = Course(
        name="Intro to RDF",
        url="https://example.com/rdf",
        description="Learn RDF dynamically",
        timeRequired="PT5H",
        isAccessibleForFree=True,
        keywords=["rdf", "python", "pydantic"],
        price=150.50
    )
    
    print("\n[OK] Course successfully instantiated!")
    print("\n--- Model Fields ---")
    for field_name, field_info in Course.model_fields.items():
        print(f" - {field_name}: type={field_info.annotation}, alias={field_info.alias}")
        
    print("\n--- Model Dump (By Alias) ---")
    print(c.model_dump(by_alias=True))
    
    print("\n--- JSON-LD Output ---")
    print(c.to_jsonld())
    
    print("\nTesting Validation Error...")
    try:
        Course(
            name="Bad Duration",
            url="https://example.com/bad",
            timeRequired="5 hours" # This should trigger our warning
        )
        print("[OK] Validation warning ran (check logs).")
    except Exception as e:
        print(f"[!] Unexpected error: {e}")

if __name__ == "__main__":
    test_dynamic_course()
