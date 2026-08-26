<script setup lang="ts">
  import type { HTMLAttributes } from 'vue'
  import { cva, type VariantProps } from 'class-variance-authority'
  import { cn } from '@/utils/css'

  // Styled via design tokens (see styles/tokens.css) — never hardcode colors.
  const buttonVariants = cva(
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-60',
    {
      variants: {
        variant: {
          primary: 'bg-primary text-primary-foreground shadow-sm hover:opacity-90',
          secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
          outline: 'border border-input bg-background text-foreground hover:bg-accent hover:text-accent-foreground',
          ghost: 'text-foreground hover:bg-accent hover:text-accent-foreground',
          destructive: 'bg-destructive text-destructive-foreground shadow-sm hover:opacity-90',
        },
        size: {
          sm: 'h-8 px-3 text-xs',
          md: 'h-9 px-4',
          lg: 'h-10 px-6 text-base',
          icon: 'h-9 w-9',
        },
      },
      defaultVariants: {
        variant: 'primary',
        size: 'md',
      },
    },
  )

  type ButtonVariants = VariantProps<typeof buttonVariants>

  const props = defineProps<{
    variant?: ButtonVariants['variant']
    size?: ButtonVariants['size']
    class?: HTMLAttributes['class']
  }>()
</script>

<template>
  <button :class="cn(buttonVariants({ variant, size }), props.class)">
    <slot />
  </button>
</template>
