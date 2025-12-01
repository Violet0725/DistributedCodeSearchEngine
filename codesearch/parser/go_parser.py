"""
Go AST parser using tree-sitter.
"""

from pathlib import Path
from typing import List, Optional
import structlog

from .base import CodeParser
from ..models import CodeEntity, CodeEntityType, Language

logger = structlog.get_logger()


class GoParser(CodeParser):
    """Parser for Go source files."""
    
    language = Language.GO
    file_extensions = ['.go']
    
    def _init_parser(self) -> None:
        """Initialize tree-sitter Go parser."""
        try:
            import tree_sitter_go as tsgo
            from tree_sitter import Language as TSLanguage, Parser
            
            self.ts_language = TSLanguage(tsgo.language())
            self.parser = Parser(self.ts_language)
            self._initialized = True
        except ImportError:
            logger.warning("tree-sitter-go not installed, using fallback parser")
            self._initialized = False
            self.parser = None
    
    def parse_file(self, file_path: Path, repo_name: str) -> List[CodeEntity]:
        """Parse a Go file and extract functions and types."""
        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
            return self.parse_content(content, str(file_path), repo_name)
        except Exception as e:
            logger.error("Failed to parse file", file=str(file_path), error=str(e))
            return []
    
    def parse_content(self, content: str, file_path: str, repo_name: str) -> List[CodeEntity]:
        """Parse Go source code and extract entities."""
        if not self._initialized:
            return self._fallback_parse(content, file_path, repo_name)
        
        entities = []
        source_bytes = content.encode('utf-8')
        
        try:
            tree = self.parser.parse(source_bytes)
            root = tree.root_node
            
            self._extract_entities(root, source_bytes, file_path, repo_name, entities)
            
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
        entities: List[CodeEntity]
    ) -> None:
        """Recursively extract code entities from AST."""
        
        # Function declarations
        if node.type == 'function_declaration':
            entity = self._parse_function(node, source_bytes, file_path, repo_name)
            if entity:
                entities.append(entity)
        
        # Method declarations (functions with receiver)
        elif node.type == 'method_declaration':
            entity = self._parse_method(node, source_bytes, file_path, repo_name)
            if entity:
                entities.append(entity)
        
        # Type declarations (structs, interfaces)
        elif node.type == 'type_declaration':
            type_entities = self._parse_type_declaration(node, source_bytes, file_path, repo_name)
            entities.extend(type_entities)
        
        for child in node.children:
            self._extract_entities(child, source_bytes, file_path, repo_name, entities)
    
    def _parse_function(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str
    ) -> Optional[CodeEntity]:
        """Parse a function declaration."""
        name = None
        parameters = []
        return_type = None
        
        for child in node.children:
            if child.type == 'identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'parameter_list':
                parameters = self._extract_parameters(child, source_bytes)
            elif child.type == 'result':
                return_type = self._get_node_text(child, source_bytes)
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_go_doc(node, source_bytes)
        
        sig = f"func {name}({', '.join(parameters)})"
        if return_type:
            sig += f" {return_type}"
        
        return CodeEntity(
            name=name,
            entity_type=CodeEntityType.FUNCTION,
            language=Language.GO,
            file_path=file_path,
            repo_name=repo_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source_code,
            docstring=docstring,
            signature=sig,
            parameters=parameters,
            return_type=return_type,
            complexity=self._calculate_complexity(node),
            loc=node.end_point[0] - node.start_point[0] + 1
        )
    
    def _parse_method(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str
    ) -> Optional[CodeEntity]:
        """Parse a method declaration (function with receiver)."""
        name = None
        receiver_type = None
        parameters = []
        return_type = None
        
        for child in node.children:
            if child.type == 'identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'parameter_list':
                # First parameter list is receiver, second is actual params
                if receiver_type is None:
                    receiver_type = self._extract_receiver(child, source_bytes)
                else:
                    parameters = self._extract_parameters(child, source_bytes)
            elif child.type == 'result':
                return_type = self._get_node_text(child, source_bytes)
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_go_doc(node, source_bytes)
        
        sig = f"func ({receiver_type}) {name}({', '.join(parameters)})"
        if return_type:
            sig += f" {return_type}"
        
        return CodeEntity(
            name=name,
            entity_type=CodeEntityType.METHOD,
            language=Language.GO,
            file_path=file_path,
            repo_name=repo_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source_code,
            docstring=docstring,
            signature=sig,
            parameters=parameters,
            return_type=return_type,
            parent_class=receiver_type,
            complexity=self._calculate_complexity(node),
            loc=node.end_point[0] - node.start_point[0] + 1
        )
    
    def _parse_type_declaration(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str
    ) -> List[CodeEntity]:
        """Parse type declarations (struct, interface)."""
        entities = []
        
        for child in node.children:
            if child.type == 'type_spec':
                entity = self._parse_type_spec(child, source_bytes, file_path, repo_name)
                if entity:
                    entities.append(entity)
        
        return entities
    
    def _parse_type_spec(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str
    ) -> Optional[CodeEntity]:
        """Parse a single type specification."""
        name = None
        type_kind = None
        
        for child in node.children:
            if child.type == 'type_identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'struct_type':
                type_kind = CodeEntityType.STRUCT
            elif child.type == 'interface_type':
                type_kind = CodeEntityType.INTERFACE
        
        if not name or not type_kind:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_go_doc(node.parent, source_bytes)
        
        sig = f"type {name} struct" if type_kind == CodeEntityType.STRUCT else f"type {name} interface"
        
        return CodeEntity(
            name=name,
            entity_type=type_kind,
            language=Language.GO,
            file_path=file_path,
            repo_name=repo_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source_code,
            docstring=docstring,
            signature=sig,
            complexity=1,
            loc=node.end_point[0] - node.start_point[0] + 1
        )
    
    def _extract_parameters(self, params_node, source_bytes: bytes) -> List[str]:
        """Extract parameter names from parameter_list."""
        params = []
        for child in params_node.children:
            if child.type == 'parameter_declaration':
                param_text = self._get_node_text(child, source_bytes).strip()
                params.append(param_text)
        return params
    
    def _extract_receiver(self, params_node, source_bytes: bytes) -> Optional[str]:
        """Extract receiver type from method declaration."""
        for child in params_node.children:
            if child.type == 'parameter_declaration':
                for subchild in child.children:
                    if subchild.type in ('type_identifier', 'pointer_type'):
                        return self._get_node_text(subchild, source_bytes)
        return None
    
    def _extract_go_doc(self, node, source_bytes: bytes) -> Optional[str]:
        """Extract Go doc comment from preceding node."""
        prev = node.prev_sibling
        while prev:
            if prev.type == 'comment':
                text = self._get_node_text(prev, source_bytes).strip()
                if text.startswith('//'):
                    return text[2:].strip()
                elif text.startswith('/*'):
                    return text[2:-2].strip()
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
        
        entities = []
        lines = content.split('\n')
        
        # Patterns
        func_pattern = re.compile(r'^func\s+(\w+)\s*\(([^)]*)\)\s*(\S.*)?{')
        method_pattern = re.compile(r'^func\s+\((\w+)\s+\*?(\w+)\)\s+(\w+)\s*\(([^)]*)\)')
        struct_pattern = re.compile(r'^type\s+(\w+)\s+struct\s*\{')
        interface_pattern = re.compile(r'^type\s+(\w+)\s+interface\s*\{')
        
        for i, line in enumerate(lines):
            # Function
            func_match = func_pattern.match(line)
            if func_match:
                name = func_match.group(1)
                params = func_match.group(2)
                ret = func_match.group(3) or ""
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.FUNCTION,
                    language=Language.GO,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"func {name}({params}) {ret}".strip(),
                    loc=1
                ))
                continue
            
            # Method
            method_match = method_pattern.match(line)
            if method_match:
                receiver_name = method_match.group(1)
                receiver_type = method_match.group(2)
                name = method_match.group(3)
                params = method_match.group(4)
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.METHOD,
                    language=Language.GO,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"func ({receiver_name} {receiver_type}) {name}({params})",
                    parent_class=receiver_type,
                    loc=1
                ))
                continue
            
            # Struct
            struct_match = struct_pattern.match(line)
            if struct_match:
                name = struct_match.group(1)
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.STRUCT,
                    language=Language.GO,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"type {name} struct",
                    loc=1
                ))
                continue
            
            # Interface
            interface_match = interface_pattern.match(line)
            if interface_match:
                name = interface_match.group(1)
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.INTERFACE,
                    language=Language.GO,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"type {name} interface",
                    loc=1
                ))
        
        return entities

