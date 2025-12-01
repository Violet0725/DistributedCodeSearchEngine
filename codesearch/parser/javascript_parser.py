"""
JavaScript/TypeScript AST parser using tree-sitter.
"""

from pathlib import Path
from typing import List, Optional
import structlog

from .base import CodeParser
from ..models import CodeEntity, CodeEntityType, Language

logger = structlog.get_logger()


class JavaScriptParser(CodeParser):
    """Parser for JavaScript and TypeScript source files."""
    
    language = Language.JAVASCRIPT
    file_extensions = ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs']
    
    def _init_parser(self) -> None:
        """Initialize tree-sitter JavaScript parser."""
        try:
            import tree_sitter_javascript as tsjs
            from tree_sitter import Language as TSLanguage, Parser
            
            self.ts_language = TSLanguage(tsjs.language())
            self.parser = Parser(self.ts_language)
            self._initialized = True
        except ImportError:
            logger.warning("tree-sitter-javascript not installed, using fallback parser")
            self._initialized = False
            self.parser = None
    
    def parse_file(self, file_path: Path, repo_name: str) -> List[CodeEntity]:
        """Parse a JavaScript file and extract functions and classes."""
        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
            return self.parse_content(content, str(file_path), repo_name)
        except Exception as e:
            logger.error("Failed to parse file", file=str(file_path), error=str(e))
            return []
    
    def parse_content(self, content: str, file_path: str, repo_name: str) -> List[CodeEntity]:
        """Parse JavaScript source code and extract entities."""
        if not self._initialized:
            return self._fallback_parse(content, file_path, repo_name)
        
        # Detect if TypeScript
        is_ts = file_path.endswith('.ts') or file_path.endswith('.tsx')
        lang = Language.TYPESCRIPT if is_ts else Language.JAVASCRIPT
        
        entities = []
        source_bytes = content.encode('utf-8')
        
        try:
            tree = self.parser.parse(source_bytes)
            root = tree.root_node
            
            self._extract_entities(root, source_bytes, file_path, repo_name, lang, entities)
            
        except Exception as e:
            logger.error("Tree-sitter parsing failed", error=str(e))
            return self._fallback_parse(content, file_path, repo_name)
        
        return entities
    
    def _extract_entities(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str,
        lang: Language,
        entities: List[CodeEntity],
        parent_class: Optional[str] = None
    ) -> None:
        """Recursively extract code entities from AST."""
        
        # Function declarations
        if node.type == 'function_declaration':
            entity = self._parse_function(node, source_bytes, file_path, repo_name, lang, parent_class)
            if entity:
                entities.append(entity)
        
        # Arrow functions assigned to variables
        elif node.type == 'lexical_declaration' or node.type == 'variable_declaration':
            for child in node.children:
                if child.type == 'variable_declarator':
                    self._parse_variable_function(child, source_bytes, file_path, repo_name, lang, entities)
        
        # Class declarations
        elif node.type == 'class_declaration':
            class_entity = self._parse_class(node, source_bytes, file_path, repo_name, lang)
            if class_entity:
                entities.append(class_entity)
                # Extract methods
                self._extract_class_methods(node, source_bytes, file_path, repo_name, lang, entities, class_entity.name)
        
        # Export statements
        elif node.type == 'export_statement':
            for child in node.children:
                self._extract_entities(child, source_bytes, file_path, repo_name, lang, entities, parent_class)
        
        # Method definitions (inside classes)
        elif node.type == 'method_definition' and parent_class:
            entity = self._parse_method(node, source_bytes, file_path, repo_name, lang, parent_class)
            if entity:
                entities.append(entity)
        
        else:
            for child in node.children:
                self._extract_entities(child, source_bytes, file_path, repo_name, lang, entities, parent_class)
    
    def _parse_function(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str,
        lang: Language,
        parent_class: Optional[str] = None
    ) -> Optional[CodeEntity]:
        """Parse a function declaration."""
        name = None
        parameters = []
        
        for child in node.children:
            if child.type == 'identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'formal_parameters':
                parameters = self._extract_parameters(child, source_bytes)
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_jsdoc(node, source_bytes)
        
        return CodeEntity(
            name=name,
            entity_type=CodeEntityType.METHOD if parent_class else CodeEntityType.FUNCTION,
            language=lang,
            file_path=file_path,
            repo_name=repo_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source_code,
            docstring=docstring,
            signature=f"function {name}({', '.join(parameters)})",
            parameters=parameters,
            parent_class=parent_class,
            complexity=self._calculate_complexity(node),
            loc=node.end_point[0] - node.start_point[0] + 1
        )
    
    def _parse_variable_function(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str,
        lang: Language,
        entities: List[CodeEntity]
    ) -> None:
        """Parse arrow functions or function expressions assigned to variables."""
        name = None
        func_node = None
        
        for child in node.children:
            if child.type == 'identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type in ('arrow_function', 'function'):
                func_node = child
        
        if not name or not func_node:
            return
        
        parameters = []
        for child in func_node.children:
            if child.type == 'formal_parameters':
                parameters = self._extract_parameters(child, source_bytes)
            elif child.type == 'identifier':
                # Single parameter arrow function: x => x + 1
                parameters = [self._get_node_text(child, source_bytes)]
        
        source_code = self._get_node_text(node.parent, source_bytes)
        
        entities.append(CodeEntity(
            name=name,
            entity_type=CodeEntityType.FUNCTION,
            language=lang,
            file_path=file_path,
            repo_name=repo_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source_code,
            signature=f"const {name} = ({', '.join(parameters)}) =>",
            parameters=parameters,
            complexity=self._calculate_complexity(func_node),
            loc=node.end_point[0] - node.start_point[0] + 1
        ))
    
    def _parse_class(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str,
        lang: Language
    ) -> Optional[CodeEntity]:
        """Parse a class declaration."""
        name = None
        extends = None
        
        for child in node.children:
            if child.type == 'identifier':
                if name is None:
                    name = self._get_node_text(child, source_bytes)
                else:
                    extends = self._get_node_text(child, source_bytes)
            elif child.type == 'class_heritage':
                for hchild in child.children:
                    if hchild.type == 'identifier':
                        extends = self._get_node_text(hchild, source_bytes)
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        signature = f"class {name}"
        if extends:
            signature += f" extends {extends}"
        
        return CodeEntity(
            name=name,
            entity_type=CodeEntityType.CLASS,
            language=lang,
            file_path=file_path,
            repo_name=repo_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source_code,
            signature=signature,
            parameters=[extends] if extends else [],
            complexity=self._calculate_complexity(node),
            loc=node.end_point[0] - node.start_point[0] + 1
        )
    
    def _extract_class_methods(
        self, 
        class_node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str,
        lang: Language,
        entities: List[CodeEntity],
        class_name: str
    ) -> None:
        """Extract methods from a class body."""
        for child in class_node.children:
            if child.type == 'class_body':
                for member in child.children:
                    if member.type == 'method_definition':
                        entity = self._parse_method(member, source_bytes, file_path, repo_name, lang, class_name)
                        if entity:
                            entities.append(entity)
    
    def _parse_method(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str,
        lang: Language,
        parent_class: str
    ) -> Optional[CodeEntity]:
        """Parse a method definition."""
        name = None
        parameters = []
        decorators = []
        
        for child in node.children:
            if child.type == 'property_identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'formal_parameters':
                parameters = self._extract_parameters(child, source_bytes)
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_jsdoc(node, source_bytes)
        
        return CodeEntity(
            name=name,
            entity_type=CodeEntityType.METHOD,
            language=lang,
            file_path=file_path,
            repo_name=repo_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source_code,
            docstring=docstring,
            signature=f"{name}({', '.join(parameters)})",
            parameters=parameters,
            parent_class=parent_class,
            decorators=decorators,
            complexity=self._calculate_complexity(node),
            loc=node.end_point[0] - node.start_point[0] + 1
        )
    
    def _extract_parameters(self, params_node, source_bytes: bytes) -> List[str]:
        """Extract parameter names from formal_parameters node."""
        params = []
        for child in params_node.children:
            if child.type == 'identifier':
                params.append(self._get_node_text(child, source_bytes))
            elif child.type in ('required_parameter', 'optional_parameter'):
                for subchild in child.children:
                    if subchild.type == 'identifier':
                        params.append(self._get_node_text(subchild, source_bytes))
                        break
            elif child.type == 'rest_pattern':
                for subchild in child.children:
                    if subchild.type == 'identifier':
                        params.append('...' + self._get_node_text(subchild, source_bytes))
                        break
        return params
    
    def _extract_jsdoc(self, node, source_bytes: bytes) -> Optional[str]:
        """Extract JSDoc comment from preceding node."""
        prev = node.prev_sibling
        while prev:
            if prev.type == 'comment':
                text = self._get_node_text(prev, source_bytes)
                if text.startswith('/**'):
                    # Clean up JSDoc
                    lines = text.split('\n')
                    clean_lines = []
                    for line in lines:
                        line = line.strip()
                        if line.startswith('/**'):
                            line = line[3:]
                        if line.endswith('*/'):
                            line = line[:-2]
                        if line.startswith('*'):
                            line = line[1:]
                        line = line.strip()
                        if line and not line.startswith('@'):
                            clean_lines.append(line)
                    return ' '.join(clean_lines) if clean_lines else None
                break
            elif prev.type not in ('comment', '\n'):
                break
            prev = prev.prev_sibling
        return None
    
    def _fallback_parse(
        self, 
        content: str, 
        file_path: str, 
        repo_name: str
    ) -> List[CodeEntity]:
        """Fallback regex-based parsing."""
        import re
        
        is_ts = file_path.endswith('.ts') or file_path.endswith('.tsx')
        lang = Language.TYPESCRIPT if is_ts else Language.JAVASCRIPT
        
        entities = []
        lines = content.split('\n')
        
        # Patterns
        func_pattern = re.compile(r'^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)')
        arrow_pattern = re.compile(r'^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>')
        class_pattern = re.compile(r'^\s*(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?')
        method_pattern = re.compile(r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{')
        
        current_class = None
        
        for i, line in enumerate(lines):
            # Class
            class_match = class_pattern.match(line)
            if class_match:
                current_class = class_match.group(1)
                extends = class_match.group(2)
                entities.append(CodeEntity(
                    name=current_class,
                    entity_type=CodeEntityType.CLASS,
                    language=lang,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"class {current_class}" + (f" extends {extends}" if extends else ""),
                    loc=1
                ))
                continue
            
            # Function
            func_match = func_pattern.match(line)
            if func_match:
                name = func_match.group(1)
                params = func_match.group(2)
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.FUNCTION,
                    language=lang,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"function {name}({params})",
                    loc=1
                ))
                continue
            
            # Arrow function
            arrow_match = arrow_pattern.match(line)
            if arrow_match:
                name = arrow_match.group(1)
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.FUNCTION,
                    language=lang,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"const {name} = () =>",
                    loc=1
                ))
                continue
            
            # Method (inside class)
            if current_class:
                method_match = method_pattern.match(line)
                if method_match:
                    name = method_match.group(1)
                    if name not in ('if', 'for', 'while', 'switch', 'catch'):
                        entities.append(CodeEntity(
                            name=name,
                            entity_type=CodeEntityType.METHOD,
                            language=lang,
                            file_path=file_path,
                            repo_name=repo_name,
                            start_line=i + 1,
                            end_line=i + 1,
                            source_code=line,
                            signature=f"{name}()",
                            parent_class=current_class,
                            loc=1
                        ))
            
            # Reset class if we see closing brace at start
            if line.strip() == '}':
                current_class = None
        
        return entities

