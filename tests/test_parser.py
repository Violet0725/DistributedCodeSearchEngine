"""
Tests for the code parser module.
"""

import pytest
from codesearch.parser import PythonParser, JavaScriptParser, GoParser, RustParser
from codesearch.models import CodeEntityType, Language


class TestPythonParser:
    """Tests for Python parser."""
    
    def setup_method(self):
        self.parser = PythonParser()
    
    def test_parse_function(self):
        """Test parsing a simple function."""
        code = '''
def hello_world(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"
'''
        entities = self.parser.parse_content(code, "test.py", "test-repo")
        
        assert len(entities) == 1
        func = entities[0]
        
        assert func.name == "hello_world"
        assert func.entity_type == CodeEntityType.FUNCTION
        assert func.language == Language.PYTHON
        assert "name" in func.parameters
        assert func.docstring == "Greet someone."
    
    def test_parse_class(self):
        """Test parsing a class with methods."""
        code = '''
class Calculator:
    """A simple calculator."""
    
    def __init__(self):
        self.result = 0
    
    def add(self, x, y):
        """Add two numbers."""
        return x + y
'''
        entities = self.parser.parse_content(code, "test.py", "test-repo")
        
        # Should find: Calculator class, __init__ method, add method
        assert len(entities) >= 2
        
        classes = [e for e in entities if e.entity_type == CodeEntityType.CLASS]
        methods = [e for e in entities if e.entity_type == CodeEntityType.METHOD]
        
        assert len(classes) == 1
        assert classes[0].name == "Calculator"
        
        assert len(methods) >= 1
        add_method = next((m for m in methods if m.name == "add"), None)
        assert add_method is not None
        assert add_method.parent_class == "Calculator"
    
    def test_parse_decorated_function(self):
        """Test parsing a decorated function."""
        code = '''
@app.route("/api")
@auth_required
def api_endpoint():
    return {"status": "ok"}
'''
        entities = self.parser.parse_content(code, "test.py", "test-repo")
        
        assert len(entities) == 1
        func = entities[0]
        
        assert func.name == "api_endpoint"
        # Decorators may or may not be captured depending on tree-sitter availability


class TestJavaScriptParser:
    """Tests for JavaScript parser."""
    
    def setup_method(self):
        self.parser = JavaScriptParser()
    
    def test_parse_function(self):
        """Test parsing a JavaScript function."""
        code = '''
function fetchData(url) {
    return fetch(url).then(r => r.json());
}
'''
        entities = self.parser.parse_content(code, "test.js", "test-repo")
        
        assert len(entities) >= 1
        func = entities[0]
        
        assert func.name == "fetchData"
        assert func.language == Language.JAVASCRIPT
    
    def test_parse_arrow_function(self):
        """Test parsing an arrow function."""
        code = '''
const processData = async (data) => {
    return data.map(x => x * 2);
};
'''
        entities = self.parser.parse_content(code, "test.js", "test-repo")
        
        # Arrow functions should be captured
        assert len(entities) >= 1
    
    def test_parse_class(self):
        """Test parsing a JavaScript class."""
        code = '''
class DataService {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }
    
    async fetch(endpoint) {
        return fetch(this.baseUrl + endpoint);
    }
}
'''
        entities = self.parser.parse_content(code, "test.js", "test-repo")
        
        classes = [e for e in entities if e.entity_type == CodeEntityType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "DataService"


class TestGoParser:
    """Tests for Go parser."""
    
    def setup_method(self):
        self.parser = GoParser()
    
    def test_parse_function(self):
        """Test parsing a Go function."""
        code = '''
func ParseJSON(data []byte) (map[string]interface{}, error) {
    var result map[string]interface{}
    err := json.Unmarshal(data, &result)
    return result, err
}
'''
        entities = self.parser.parse_content(code, "test.go", "test-repo")
        
        assert len(entities) >= 1
        func = entities[0]
        
        assert func.name == "ParseJSON"
        assert func.language == Language.GO
    
    def test_parse_method(self):
        """Test parsing a Go method."""
        code = '''
func (s *Server) HandleRequest(w http.ResponseWriter, r *http.Request) {
    w.Write([]byte("OK"))
}
'''
        entities = self.parser.parse_content(code, "test.go", "test-repo")
        
        assert len(entities) >= 1
        method = entities[0]
        
        assert method.name == "HandleRequest"
        assert method.entity_type == CodeEntityType.METHOD
    
    def test_parse_struct(self):
        """Test parsing a Go struct."""
        code = '''
type Config struct {
    Host string
    Port int
}
'''
        entities = self.parser.parse_content(code, "test.go", "test-repo")
        
        structs = [e for e in entities if e.entity_type == CodeEntityType.STRUCT]
        assert len(structs) == 1
        assert structs[0].name == "Config"


class TestRustParser:
    """Tests for Rust parser."""
    
    def setup_method(self):
        self.parser = RustParser()
    
    def test_parse_function(self):
        """Test parsing a Rust function."""
        code = '''
pub fn process_data(input: &str) -> Result<Vec<u8>, Error> {
    input.as_bytes().to_vec()
}
'''
        entities = self.parser.parse_content(code, "test.rs", "test-repo")
        
        assert len(entities) >= 1
        func = entities[0]
        
        assert func.name == "process_data"
        assert func.language == Language.RUST
    
    def test_parse_struct(self):
        """Test parsing a Rust struct."""
        code = '''
pub struct HttpClient {
    base_url: String,
    timeout: Duration,
}
'''
        entities = self.parser.parse_content(code, "test.rs", "test-repo")
        
        structs = [e for e in entities if e.entity_type == CodeEntityType.STRUCT]
        assert len(structs) == 1
        assert structs[0].name == "HttpClient"
    
    def test_parse_impl(self):
        """Test parsing a Rust impl block."""
        code = '''
impl HttpClient {
    pub fn new(base_url: &str) -> Self {
        Self { base_url: base_url.to_string(), timeout: Duration::from_secs(30) }
    }
    
    pub async fn get(&self, path: &str) -> Result<Response, Error> {
        // implementation
    }
}
'''
        entities = self.parser.parse_content(code, "test.rs", "test-repo")
        
        methods = [e for e in entities if e.entity_type == CodeEntityType.METHOD]
        assert len(methods) >= 1
        
        # Methods should have HttpClient as parent
        for method in methods:
            assert method.parent_class == "HttpClient"

