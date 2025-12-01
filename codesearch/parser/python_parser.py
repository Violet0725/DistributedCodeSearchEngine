"""
Python-specific AST parser using tree-sitter.
"""

from pathlib import Path
from typing import List, Optional, Tuple
import structlog

from .base import CodeParser
from ..models import CodeEntity, CodeEntityType, Language

logger = structlog.get_logger()


class PythonParser(CodeParser):
    """Parser for Python source files."""
    
    language = Language.PYTHON
    file_extensions = ['.py', '.pyw']
    
    def _init_parser(self) -> None:
        """Initialize tree-sitter Python parser."""
        try:
            import tree_sitter_python as tspython
            from tree_sitter import Language as TSLanguage, Parser
            
            self.ts_language = TSLanguage(tspython.language())
            self.parser = Parser(self.ts_language)
            self._initialized = True
        except ImportError:
            logger.warning("tree-sitter-python not installed, using fallback parser")
            self._initialized = False
            self.parser = None
    
    def parse_file(self, file_path: Path, repo_name: str) -> List[CodeEntity]:
        """Parse a Python file and extract functions and classes."""
        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
            return self.parse_content(content, str(file_path), repo_name)
        except Exception as e:
            logger.error("Failed to parse file", file=str(file_path), error=str(e))
            return []
    
    def parse_content(self, content: str, file_path: str, repo_name: str) -> List[CodeEntity]:
        """Parse Python source code and extract entities."""
        if not self._initialized:
            return self._fallback_parse(content, file_path, repo_name)
        
        entities = []
        source_bytes = content.encode('utf-8')
        
        try:
            tree = self.parser.parse(source_bytes)
            root = tree.root_node
            
            # Extract functions and classes
            entities.extend(self._extract_functions(root, source_bytes, file_path, repo_name))
            entities.extend(self._extract_classes(root, source_bytes, file_path, repo_name))
            
        except Exception as e:
            logger.error("Tree-sitter parsing failed", error=str(e))
            return self._fallback_parse(content, file_path, repo_name)
        
        return entities
    
    def _extract_functions(
        self, 
        root_node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str,
        parent_class: Optional[str] = None
    ) -> List[CodeEntity]:
        """Extract function definitions from AST."""
        entities = []
        
        def visit(node, current_class=None):
            if node.type == 'function_definition':
                entity = self._parse_function_node(
                    node, source_bytes, file_path, repo_name, current_class
                )
                if entity:
                    entities.append(entity)
            
            elif node.type == 'class_definition':
                # Get class name for methods
                class_name = None
                for child in node.children:
                    if child.type == 'identifier':
                        class_name = self._get_node_text(child, source_bytes)
                        break
                
                # Visit class body for methods
                for child in node.children:
                    if child.type == 'block':
                        for stmt in child.children:
                            visit(stmt, class_name)
            else:
                for child in node.children:
                    visit(child, current_class)
        
        visit(root_node, parent_class)
        return entities
    
    def _parse_function_node(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str,
        parent_class: Optional[str] = None
    ) -> Optional[CodeEntity]:
        """Parse a function_definition node into a CodeEntity."""
        name = None
        parameters = []
        return_type = None
        decorators = []
        
        # Extract function components
        for child in node.children:
            if child.type == 'identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'parameters':
                parameters = self._extract_parameters(child, source_bytes)
            elif child.type == 'type':
                return_type = self._get_node_text(child, source_bytes)
        
        # Get decorators (look at previous siblings)
        prev = node.prev_sibling
        while prev and prev.type == 'decorator':
            dec_text = self._get_node_text(prev, source_bytes)
            decorators.insert(0, dec_text)
            prev = prev.prev_sibling
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_python_docstring(node, source_bytes)
        signature = self._build_signature(name, parameters, return_type)
        
        entity_type = CodeEntityType.METHOD if parent_class else CodeEntityType.FUNCTION
        
        return CodeEntity(
            name=name,
            entity_type=entity_type,
            language=Language.PYTHON,
            file_path=file_path,
            repo_name=repo_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source_code,
            docstring=docstring,
            signature=signature,
            parameters=parameters,
            return_type=return_type,
            decorators=decorators,
            parent_class=parent_class,
            complexity=self._calculate_complexity(node),
            loc=node.end_point[0] - node.start_point[0] + 1
        )
    
    def _extract_classes(
        self, 
        root_node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str
    ) -> List[CodeEntity]:
        """Extract class definitions from AST."""
        entities = []
        
        def visit(node):
            if node.type == 'class_definition':
                entity = self._parse_class_node(node, source_bytes, file_path, repo_name)
                if entity:
                    entities.append(entity)
            
            for child in node.children:
                if child.type != 'class_definition':  # Don't recurse into nested classes here
                    visit(child)
        
        visit(root_node)
        return entities
    
    def _parse_class_node(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str
    ) -> Optional[CodeEntity]:
        """Parse a class_definition node into a CodeEntity."""
        name = None
        decorators = []
        bases = []
        
        for child in node.children:
            if child.type == 'identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'argument_list':
                # Base classes
                for arg in child.children:
                    if arg.type == 'identifier':
                        bases.append(self._get_node_text(arg, source_bytes))
        
        # Get decorators
        prev = node.prev_sibling
        while prev and prev.type == 'decorator':
            dec_text = self._get_node_text(prev, source_bytes)
            decorators.insert(0, dec_text)
            prev = prev.prev_sibling
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_python_docstring(node, source_bytes)
        signature = f"class {name}" + (f"({', '.join(bases)})" if bases else "")
        
        return CodeEntity(
            name=name,
            entity_type=CodeEntityType.CLASS,
            language=Language.PYTHON,
            file_path=file_path,
            repo_name=repo_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source_code,
            docstring=docstring,
            signature=signature,
            parameters=bases,  # Store base classes in parameters
            decorators=decorators,
            complexity=self._calculate_complexity(node),
            loc=node.end_point[0] - node.start_point[0] + 1
        )
    
    def _extract_parameters(self, params_node, source_bytes: bytes) -> List[str]:
        """Extract parameter names from a parameters node."""
        params = []
        for child in params_node.children:
            if child.type == 'identifier':
                params.append(self._get_node_text(child, source_bytes))
            elif child.type in ('default_parameter', 'typed_parameter', 'typed_default_parameter'):
                # Get the parameter name from compound parameter types
                for subchild in child.children:
                    if subchild.type == 'identifier':
                        params.append(self._get_node_text(subchild, source_bytes))
                        break
            elif child.type == 'list_splat_pattern':  # *args
                for subchild in child.children:
                    if subchild.type == 'identifier':
                        params.append('*' + self._get_node_text(subchild, source_bytes))
                        break
            elif child.type == 'dictionary_splat_pattern':  # **kwargs
                for subchild in child.children:
                    if subchild.type == 'identifier':
                        params.append('**' + self._get_node_text(subchild, source_bytes))
                        break
        return params
    
    def _extract_python_docstring(self, node, source_bytes: bytes) -> Optional[str]:
        """Extract docstring from a Python function or class."""
        # Find the block/body
        for child in node.children:
            if child.type == 'block':
                # First statement in block might be docstring
                for stmt in child.children:
                    if stmt.type == 'expression_statement':
                        for expr in stmt.children:
                            if expr.type == 'string':
                                docstring = self._get_node_text(expr, source_bytes)
                                # Clean up the docstring
                                return docstring.strip('"""\'\'\'').strip()
                    break  # Only check first statement
        return None
    
    def _build_signature(
        self, 
        name: str, 
        params: List[str], 
        return_type: Optional[str]
    ) -> str:
        """Build a function signature string."""
        sig = f"def {name}({', '.join(params)})"
        if return_type:
            sig += f" -> {return_type}"
        return sig
    
    def _fallback_parse(
        self, 
        content: str, 
        file_path: str, 
        repo_name: str
    ) -> List[CodeEntity]:
        """Fallback regex-based parsing when tree-sitter isn't available."""
        import re
        
        entities = []
        lines = content.split('\n')
        
        # Simple regex patterns for functions and classes
        func_pattern = re.compile(r'^(\s*)def\s+(\w+)\s*\(([^)]*)\)')
        class_pattern = re.compile(r'^(\s*)class\s+(\w+)(?:\s*\(([^)]*)\))?')
        
        current_class = None
        class_indent = 0
        
        for i, line in enumerate(lines):
            # Check for class definition
            class_match = class_pattern.match(line)
            if class_match:
                indent = len(class_match.group(1))
                name = class_match.group(2)
                bases = class_match.group(3) or ""
                
                current_class = name
                class_indent = indent
                
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.CLASS,
                    language=Language.PYTHON,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"class {name}({bases})" if bases else f"class {name}",
                    parameters=[b.strip() for b in bases.split(',') if b.strip()],
                    loc=1
                ))
                continue
            
            # Check for function definition
            func_match = func_pattern.match(line)
            if func_match:
                indent = len(func_match.group(1))
                name = func_match.group(2)
                params = func_match.group(3)
                
                # Determine if it's a method or function
                is_method = current_class and indent > class_indent
                parent = current_class if is_method else None
                
                param_list = [p.strip().split(':')[0].split('=')[0].strip() 
                             for p in params.split(',') if p.strip()]
                
                # Extract full function body
                func_start = i
                func_end = i
                func_lines = [line]
                
                # Find the end of the function by tracking indentation
                for j in range(i + 1, len(lines)):
                    next_line = lines[j]
                    if not next_line.strip():  # Empty line, continue
                        func_lines.append(next_line)
                        continue
                    
                    next_indent = len(next_line) - len(next_line.lstrip())
                    
                    # If we hit a line at same or less indent (and not empty), function ended
                    if next_indent <= indent and next_line.strip():
                        break
                    
                    func_lines.append(next_line)
                    func_end = j
                
                full_source = '\n'.join(func_lines)
                
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.METHOD if is_method else CodeEntityType.FUNCTION,
                    language=Language.PYTHON,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=func_start + 1,
                    end_line=func_end + 1,
                    source_code=full_source,
                    signature=f"def {name}({params})",
                    parameters=param_list,
                    parent_class=parent,
                    loc=func_end - func_start + 1
                ))
            
            # Reset class context if we're back at module level
            if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                if not class_match:
                    current_class = None
        
        return entities

