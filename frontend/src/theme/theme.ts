import { createTheme } from '@mui/material/styles'

const ink = 'midnightblue'
const muted = 'darkslateblue'

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: 'navy',
      light: 'steelblue',
      dark: 'midnightblue',
      contrastText: 'white',
    },
    secondary: {
      main: 'darkgreen',
      light: 'seagreen',
      dark: 'darkgreen',
      contrastText: 'white',
    },
    success: {
      main: 'seagreen',
      light: 'mediumseagreen',
      dark: 'darkgreen',
      contrastText: 'white',
    },
    warning: {
      main: 'darkorange',
      light: 'orange',
      dark: 'saddlebrown',
      contrastText: 'black',
    },
    error: {
      main: 'firebrick',
      light: 'indianred',
      dark: 'darkred',
      contrastText: 'white',
    },
    info: {
      main: 'steelblue',
      light: 'skyblue',
      dark: 'navy',
      contrastText: 'white',
    },
    background: {
      default: 'whitesmoke',
      paper: 'white',
    },
    text: {
      primary: ink,
      secondary: muted,
      disabled: 'gray',
    },
    divider: 'lightgray',
    action: {
      active: ink,
      hover: 'floralwhite',
      selected: 'floralwhite',
      disabled: 'gray',
      disabledBackground: 'gainsboro',
      focus: 'darkorange',
    },
  },
  shape: {
    borderRadius: 5,
  },
  typography: {
    fontFamily:
      '"Segoe UI Variable Text", "Segoe UI", "Nirmala UI", "Noto Sans Tamil", "Noto Sans Devanagari", sans-serif',
    fontSize: 16,
    h1: { fontSize: '2.75rem', lineHeight: 1.12, fontWeight: 700, letterSpacing: '-0.02em' },
    h2: { fontSize: '2.25rem', lineHeight: 1.2, fontWeight: 700, letterSpacing: '-0.015em' },
    h3: { fontSize: '1.5rem', lineHeight: 1.35, fontWeight: 700 },
    h4: { fontSize: '1.375rem', lineHeight: 1.35, fontWeight: 700 },
    h5: { fontSize: '1.25rem', lineHeight: 1.4, fontWeight: 700 },
    h6: { fontSize: '1.125rem', lineHeight: 1.45, fontWeight: 700 },
    body1: { fontSize: '1.125rem', lineHeight: 1.65 },
    body2: { fontSize: '1.0625rem', lineHeight: 1.6 },
    caption: { fontSize: '0.9rem', lineHeight: 1.5 },
    button: { fontSize: '1.125rem', fontWeight: 650, textTransform: 'none' },
  },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          minHeight: 48,
          paddingInline: 20,
          borderRadius: 2,
          boxShadow: 'none',
          '&.Mui-disabled': {
            color: 'darkslategray',
            backgroundColor: 'gainsboro',
          },
        },
        sizeLarge: { minHeight: 56, fontSize: '1.125rem' },
        contained: {
          '&:hover': { boxShadow: 'none' },
        },
        containedPrimary: {
          '&:hover': { backgroundColor: 'midnightblue' },
        },
        containedSecondary: {
          '&:hover': { backgroundColor: 'midnightblue' },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: { root: { minWidth: 48, minHeight: 48 } },
    },
    MuiTextField: {
      defaultProps: { fullWidth: true, margin: 'normal' },
    },
    MuiInputBase: {
      styleOverrides: {
        input: { minHeight: 28 },
        root: { fontSize: '1.125rem', backgroundColor: 'white' },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 2,
          '& .MuiOutlinedInput-notchedOutline': { borderColor: 'darkgray' },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'darkgreen' },
          '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: 'darkgreen',
            borderWidth: 2,
          },
        },
      },
    },
    MuiMenuItem: {
      styleOverrides: { root: { minHeight: 48, fontSize: '1rem' } },
    },
    MuiListItemButton: {
      styleOverrides: { root: { minHeight: 56 } },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontSize: '1rem', height: 40, borderRadius: 5 },
        outlined: { borderColor: 'darkgray' },
      },
    },
    MuiFormHelperText: {
      styleOverrides: { root: { fontSize: '0.9rem', lineHeight: 1.5 } },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 2,
          border: 0,
          borderLeft: '4px solid navy',
          boxShadow: 'none',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: 'none' },
        elevation1: { boxShadow: 'none' },
        elevation2: { boxShadow: 'none' },
        elevation3: { boxShadow: 'none' },
        elevation4: { boxShadow: 'none' },
        elevation8: { boxShadow: 'none' },
      },
    },
    MuiAlert: {
      styleOverrides: { root: { fontSize: '1rem', borderRadius: 2 } },
    },
    MuiStepLabel: {
      styleOverrides: { label: { fontSize: '1rem' } },
    },
    MuiBottomNavigationAction: {
      styleOverrides: {
        root: {
          minHeight: 64,
          color: 'dimgray',
          '&.Mui-selected': { color: 'navy' },
          '&:hover': { backgroundColor: 'floralwhite' },
        },
        label: { fontSize: '1rem', '&.Mui-selected': { fontSize: '1rem' } },
      },
    },
  },
})
