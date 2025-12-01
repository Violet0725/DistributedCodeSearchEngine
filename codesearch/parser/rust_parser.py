"""
Rust AST parser using tree-sitter.
"""

from pathlib import Path
from typing import List, Optional
import structlog

from .base import CodeParser
from ..models import CodeEntity, CodeEntityType, Language

logger = structlog.get_logger()


class RustParser(CodeParser):
    """Parser for Rust source files."""
    
    language = Language.RUST
    file_extensions = ['.rs']
    
    def _init_parser(self) -> None:
        """Initialize tree-sitter Rust parser."""
        try:
            import tree_sitter_rust as tsrust
            from tree_sitter import Language as TSLanguage, Parser
            
            self.ts_language = TSLanguage(tsrust.language())
            self.parser = Parser(self.ts_language)
            self._initialized = True
        except ImportError:
            logger.warning("tree-sitter-rust not installed, using fallback parser")
            self._initialized = False
            self.parser = None
    
    def parse_file(self, file_path: Path, repo_name: str) -> List[CodeEntity]:
        """Parse a Rust file and extract functions and types."""
        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
            return self.parse_content(content, str(file_path), repo_name)
        except Exception as e:
            logger.error("Failed to parse file", file=str(file_path), error=str(e))
            return []
    
    def parse_content(self, content: str, file_path: str, repo_name: str) -> List[CodeEntity]:
        """Parse Rust source code and extract entities."""
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
        entities: List[CodeEntity],
        impl_type: Optional[str] = None
    ) -> None:
        """Recursively extract code entities from AST."""
        
        # Function items
        if node.type == 'function_item':
            entity = self._parse_function(node, source_bytes, file_path, repo_name, impl_type)
            if entity:
                entities.append(entity)
        
        # Struct definitions
        elif node.type == 'struct_item':
            entity = self._parse_struct(node, source_bytes, file_path, repo_name)
            if entity:
                entities.append(entity)
        
        # Enum definitions
        elif node.type == 'enum_item':
            entity = self._parse_enum(node, source_bytes, file_path, repo_name)
            if entity:
                entities.append(entity)
        
        # Trait definitions
        elif node.type == 'trait_item':
            entity = self._parse_trait(node, source_bytes, file_path, repo_name)
            if entity:
                entities.append(entity)
        
        # Impl blocks
        elif node.type == 'impl_item':
            impl_name = self._get_impl_type(node, source_bytes)
            for child in node.children:
                self._extract_entities(child, source_bytes, file_path, repo_name, entities, impl_name)
            return  # Don't recurse children again
        
        for child in node.children:
            self._extract_entities(child, source_bytes, file_path, repo_name, entities, impl_type)
    
    def _parse_function(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str,
        impl_type: Optional[str] = None
    ) -> Optional[CodeEntity]:
        """Parse a function item."""
        name = None
        parameters = []
        return_type = None
        is_public = False
        is_async = False
        
        for child in node.children:
            if child.type == 'identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'parameters':
                parameters = self._extract_parameters(child, source_bytes)
            elif child.type == 'return_type' or child.type == 'type':
                return_type = self._get_node_text(child, source_bytes).lstrip('-> ').strip()
            elif child.type == 'visibility_modifier':
                is_public = 'pub' in self._get_node_text(child, source_bytes)
            elif child.type == 'async':
                is_async = True
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_rust_doc(node, source_bytes)
        
        # Build signature
        sig_parts = []
        if is_public:
            sig_parts.append("pub")
        if is_async:
            sig_parts.append("async")
        sig_parts.append("fn")
        sig_parts.append(f"{name}({', '.join(parameters)})")
        if return_type:
            sig_parts.append(f"-> {return_type}")
        
        entity_type = CodeEntityType.METHOD if impl_type else CodeEntityType.FUNCTION
        
        return CodeEntity(
            name=name,
            entity_type=entity_type,
            language=Language.RUST,
            file_path=file_path,
            repo_name=repo_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source_code,
            docstring=docstring,
            signature=' '.join(sig_parts),
            parameters=parameters,
            return_type=return_type,
            parent_class=impl_type,
            complexity=self._calculate_complexity(node),
            loc=node.end_point[0] - node.start_point[0] + 1
        )
    
    def _parse_struct(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str
    ) -> Optional[CodeEntity]:
        """Parse a struct definition."""
        name = None
        is_public = False
        
        for child in node.children:
            if child.type == 'type_identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'visibility_modifier':
                is_public = 'pub' in self._get_node_text(child, source_bytes)
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_rust_doc(node, source_bytes)
        
        sig = "pub struct " if is_public else "struct "
        sig += name
        
        return CodeEntity(
            name=name,
            entity_type=CodeEntityType.STRUCT,
            language=Language.RUST,
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
    
    def _parse_enum(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str
    ) -> Optional[CodeEntity]:
        """Parse an enum definition."""
        name = None
        is_public = False
        
        for child in node.children:
            if child.type == 'type_identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'visibility_modifier':
                is_public = 'pub' in self._get_node_text(child, source_bytes)
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_rust_doc(node, source_bytes)
        
        sig = "pub enum " if is_public else "enum "
        sig += name
        
        return CodeEntity(
            name=name,
            entity_type=CodeEntityType.ENUM,
            language=Language.RUST,
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
    
    def _parse_trait(
        self, 
        node, 
        source_bytes: bytes, 
        file_path: str, 
        repo_name: str
    ) -> Optional[CodeEntity]:
        """Parse a trait definition."""
        name = None
        is_public = False
        
        for child in node.children:
            if child.type == 'type_identifier':
                name = self._get_node_text(child, source_bytes)
            elif child.type == 'visibility_modifier':
                is_public = 'pub' in self._get_node_text(child, source_bytes)
        
        if not name:
            return None
        
        source_code = self._get_node_text(node, source_bytes)
        docstring = self._extract_rust_doc(node, source_bytes)
        
        sig = "pub trait " if is_public else "trait "
        sig += name
        
        return CodeEntity(
            name=name,
            entity_type=CodeEntityType.INTERFACE,  # Traits are like interfaces
            language=Language.RUST,
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
    
    def _get_impl_type(self, node, source_bytes: bytes) -> Optional[str]:
        """Get the type name from an impl block."""
        for child in node.children:
            if child.type == 'type_identifier':
                return self._get_node_text(child, source_bytes)
            elif child.type == 'generic_type':
                for subchild in child.children:
                    if subchild.type == 'type_identifier':
                        return self._get_node_text(subchild, source_bytes)
        return None
    
    def _extract_parameters(self, params_node, source_bytes: bytes) -> List[str]:
        """Extract parameter names from parameters node."""
        params = []
        for child in params_node.children:
            if child.type == 'parameter':
                param_text = self._get_node_text(child, source_bytes).strip()
                params.append(param_text)
            elif child.type == 'self_parameter':
                params.append(self._get_node_text(child, source_bytes).strip())
        return params
    
    def _extract_rust_doc(self, node, source_bytes: bytes) -> Optional[str]:
        """Extract Rust doc comment (/// or //!) from preceding nodes."""
        doc_lines = []
        prev = node.prev_sibling
        
        while prev:
            if prev.type in ('line_comment', 'block_comment'):
                text = self._get_node_text(prev, source_bytes).strip()
                if text.startswith('///') or text.startswith('//!'):
                    doc_lines.insert(0, text[3:].strip())
                elif text.startswith('/**') or text.startswith('/*!'):
                    doc_lines.insert(0, text[3:-2].strip())
                else:
                    break
            elif prev.type == 'attribute_item':
                # Skip attributes
                pass
            else:
                break
            prev = prev.prev_sibling
        
        return ' '.join(doc_lines) if doc_lines else None
    
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
        func_pattern = re.compile(r'^(\s*)(pub\s+)?(async\s+)?fn\s+(\w+)\s*(<[^>]*>)?\s*\(([^)]*)\)')
        struct_pattern = re.compile(r'^(\s*)(pub\s+)?struct\s+(\w+)')
        enum_pattern = re.compile(r'^(\s*)(pub\s+)?enum\s+(\w+)')
        trait_pattern = re.compile(r'^(\s*)(pub\s+)?trait\s+(\w+)')
        impl_pattern = re.compile(r'^impl\s*(?:<[^>]*>\s*)?(\w+)')
        
        current_impl = None
        
        for i, line in enumerate(lines):
            # Impl block
            impl_match = impl_pattern.match(line)
            if impl_match:
                current_impl = impl_match.group(1)
                continue
            
            # Function
            func_match = func_pattern.match(line)
            if func_match:
                is_pub = bool(func_match.group(2))
                is_async = bool(func_match.group(3))
                name = func_match.group(4)
                params = func_match.group(6)
                
                sig_parts = []
                if is_pub:
                    sig_parts.append("pub")
                if is_async:
                    sig_parts.append("async")
                sig_parts.append(f"fn {name}({params})")
                
                entity_type = CodeEntityType.METHOD if current_impl else CodeEntityType.FUNCTION
                
                entities.append(CodeEntity(
                    name=name,
                    entity_type=entity_type,
                    language=Language.RUST,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=' '.join(sig_parts),
                    parent_class=current_impl,
                    loc=1
                ))
                continue
            
            # Struct
            struct_match = struct_pattern.match(line)
            if struct_match:
                is_pub = bool(struct_match.group(2))
                name = struct_match.group(3)
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.STRUCT,
                    language=Language.RUST,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"{'pub ' if is_pub else ''}struct {name}",
                    loc=1
                ))
                current_impl = None
                continue
            
            # Enum
            enum_match = enum_pattern.match(line)
            if enum_match:
                is_pub = bool(enum_match.group(2))
                name = enum_match.group(3)
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.ENUM,
                    language=Language.RUST,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"{'pub ' if is_pub else ''}enum {name}",
                    loc=1
                ))
                current_impl = None
                continue
            
            # Trait
            trait_match = trait_pattern.match(line)
            if trait_match:
                is_pub = bool(trait_match.group(2))
                name = trait_match.group(3)
                entities.append(CodeEntity(
                    name=name,
                    entity_type=CodeEntityType.INTERFACE,
                    language=Language.RUST,
                    file_path=file_path,
                    repo_name=repo_name,
                    start_line=i + 1,
                    end_line=i + 1,
                    source_code=line,
                    signature=f"{'pub ' if is_pub else ''}trait {name}",
                    loc=1
                ))
                current_impl = None
                continue
            
            # End of impl block
            if line.strip() == '}' and not line.startswith(' '):
                current_impl = None
        
        return entities

