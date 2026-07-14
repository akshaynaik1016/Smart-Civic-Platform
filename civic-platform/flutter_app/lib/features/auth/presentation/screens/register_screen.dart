import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:pinput/pinput.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../shared/widgets/app_text_field.dart';
import '../../../../shared/widgets/loading_button.dart';
import '../bloc/auth_bloc.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey    = GlobalKey<FormState>();
  final _nameCtrl   = TextEditingController();
  final _emailCtrl  = TextEditingController();
  final _phoneCtrl  = TextEditingController();
  final _passCtrl   = TextEditingController();
  final _confirmCtrl= TextEditingController();
  bool  _obscure    = true;
  bool  _otpStep    = false;

  @override
  void dispose() {
    _nameCtrl.dispose(); _emailCtrl.dispose();
    _phoneCtrl.dispose(); _passCtrl.dispose(); _confirmCtrl.dispose();
    super.dispose();
  }

  void _submit() {
    if (_formKey.currentState!.validate()) {
      context.read<AuthBloc>().add(AuthRegisterRequested(
        fullName: _nameCtrl.text.trim(),
        email:    _emailCtrl.text.trim(),
        phone:    _phoneCtrl.text.trim(),
        password: _passCtrl.text,
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Create Account'),
        leading: BackButton(onPressed: () => context.pop()),
      ),
      body: BlocConsumer<AuthBloc, AuthState>(
        listener: (context, state) {
          if (state is AuthOtpRequired) {
            setState(() => _otpStep = true);
          } else if (state is AuthError) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(state.message),
                backgroundColor: Colors.red.shade700,
                behavior: SnackBarBehavior.floating,
              ),
            );
          }
        },
        builder: (context, state) {
          if (_otpStep) return _OtpStep(isLoading: state is AuthLoading);

          return SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Join Smart Civic', style: Theme.of(context).textTheme.headlineMedium),
                  const SizedBox(height: 8),
                  Text(
                    'Create your account to report civic issues and track resolution.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: AppColors.onSurfaceVar),
                  ),
                  const SizedBox(height: 32),

                  AppTextField(
                    controller: _nameCtrl,
                    label: 'Full name',
                    hint: 'Ravi Kumar',
                    prefixIcon: Icons.person_outline_rounded,
                    textInputAction: TextInputAction.next,
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Full name is required';
                      if (v.trim().length < 3) return 'Name too short';
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),

                  AppTextField(
                    controller: _emailCtrl,
                    label: 'Email address',
                    hint: 'ravi@example.com',
                    prefixIcon: Icons.email_outlined,
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.next,
                    validator: (v) {
                      if (v == null || v.isEmpty) return 'Email is required';
                      if (!RegExp(r'^[\w.-]+@[\w.-]+\.\w+$').hasMatch(v)) return 'Invalid email';
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),

                  AppTextField(
                    controller: _phoneCtrl,
                    label: 'Phone number',
                    hint: '+91 9876543210',
                    prefixIcon: Icons.phone_outlined,
                    keyboardType: TextInputType.phone,
                    textInputAction: TextInputAction.next,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    validator: (v) {
                      if (v == null || v.isEmpty) return 'Phone is required';
                      if (v.length < 10) return 'Enter 10-digit mobile number';
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),

                  AppTextField(
                    controller: _passCtrl,
                    label: 'Password',
                    hint: 'Min 8 characters',
                    prefixIcon: Icons.lock_outline_rounded,
                    obscureText: _obscure,
                    textInputAction: TextInputAction.next,
                    suffixIcon: IconButton(
                      icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                      onPressed: () => setState(() => _obscure = !_obscure),
                    ),
                    validator: (v) {
                      if (v == null || v.isEmpty) return 'Password is required';
                      if (v.length < 8) return 'Minimum 8 characters';
                      if (!RegExp(r'(?=.*[A-Z])').hasMatch(v)) return 'Include at least one uppercase letter';
                      if (!RegExp(r'(?=.*\d)').hasMatch(v))    return 'Include at least one number';
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),

                  AppTextField(
                    controller: _confirmCtrl,
                    label: 'Confirm password',
                    hint: 'Re-enter password',
                    prefixIcon: Icons.lock_outline_rounded,
                    obscureText: _obscure,
                    textInputAction: TextInputAction.done,
                    onFieldSubmitted: (_) => _submit(),
                    validator: (v) {
                      if (v != _passCtrl.text) return 'Passwords do not match';
                      return null;
                    },
                  ),
                  const SizedBox(height: 32),

                  LoadingButton(
                    label: 'Create Account',
                    isLoading: state is AuthLoading,
                    onPressed: _submit,
                  ),
                  const SizedBox(height: 24),

                  Center(
                    child: Text.rich(
                      TextSpan(
                        text: 'By registering, you agree to our ',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(color: AppColors.onSurfaceVar),
                        children: [
                          TextSpan(
                            text: 'Terms & Privacy Policy',
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.primary,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _OtpStep extends StatelessWidget {
  final bool isLoading;
  const _OtpStep({required this.isLoading});

  @override
  Widget build(BuildContext context) {
    String otp = '';
    final defaultPinTheme = PinTheme(
      width: 54, height: 60,
      textStyle: const TextStyle(fontFamily: 'Poppins', fontSize: 22, fontWeight: FontWeight.w700),
      decoration: BoxDecoration(
        color: AppColors.surfaceVariant,
        borderRadius: BorderRadius.circular(14),
      ),
    );

    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 24),
          const Icon(Icons.verified_user_outlined, color: AppColors.primary, size: 48),
          const SizedBox(height: 24),
          Text('Verify your account', style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 8),
          Text(
            'Enter the 6-digit OTP sent to your phone number.',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: AppColors.onSurfaceVar),
          ),
          const SizedBox(height: 40),
          Pinput(
            length: 6,
            defaultPinTheme: defaultPinTheme,
            focusedPinTheme: defaultPinTheme.copyWith(
              decoration: defaultPinTheme.decoration!.copyWith(
                border: Border.all(color: AppColors.primary, width: 2),
              ),
            ),
            onChanged: (v) => otp = v,
            onCompleted: (v) {
              otp = v;
              context.read<AuthBloc>().add(AuthOtpRequested(otp: v));
            },
          ),
          const SizedBox(height: 32),
          LoadingButton(
            label: 'Verify OTP',
            isLoading: isLoading,
            onPressed: () {
              if (otp.length == 6) {
                context.read<AuthBloc>().add(AuthOtpRequested(otp: otp));
              }
            },
          ),
          const SizedBox(height: 16),
          Center(
            child: TextButton(
              onPressed: () {},
              child: const Text("Didn't receive OTP? Resend"),
            ),
          ),
        ],
      ),
    );
  }
}
