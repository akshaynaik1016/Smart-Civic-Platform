import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class AppTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String? hint;
  final IconData? prefixIcon;
  final Widget? suffixIcon;
  final bool obscureText;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final String? Function(String?)? validator;
  final void Function(String)? onFieldSubmitted;
  final void Function(String)? onChanged;
  final int? maxLines;
  final List<TextInputFormatter>? inputFormatters;
  final bool enabled;
  final bool autofocus;
  final FocusNode? focusNode;

  const AppTextField({
    super.key,
    required this.controller,
    required this.label,
    this.hint,
    this.prefixIcon,
    this.suffixIcon,
    this.obscureText = false,
    this.keyboardType,
    this.textInputAction,
    this.validator,
    this.onFieldSubmitted,
    this.onChanged,
    this.maxLines = 1,
    this.inputFormatters,
    this.enabled = true,
    this.autofocus = false,
    this.focusNode,
  });

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller:       controller,
      obscureText:      obscureText,
      keyboardType:     keyboardType,
      textInputAction:  textInputAction,
      validator:        validator,
      onFieldSubmitted: onFieldSubmitted,
      onChanged:        onChanged,
      maxLines:         obscureText ? 1 : maxLines,
      inputFormatters:  inputFormatters,
      enabled:          enabled,
      autofocus:        autofocus,
      focusNode:        focusNode,
      style: Theme.of(context).textTheme.bodyLarge,
      decoration: InputDecoration(
        labelText:   label,
        hintText:    hint,
        prefixIcon:  prefixIcon != null
            ? Icon(prefixIcon, size: 20,
                color: Theme.of(context).colorScheme.onSurfaceVariant)
            : null,
        suffixIcon:  suffixIcon,
        alignLabelWithHint: (maxLines ?? 1) > 1,
      ),
    );
  }
}