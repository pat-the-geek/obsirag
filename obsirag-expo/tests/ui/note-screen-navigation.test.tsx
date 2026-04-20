import React from 'react';
import renderer, { act } from 'react-test-renderer';

const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockUseLocalSearchParams = jest.fn();
const mockUseNoteDetail = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  useLocalSearchParams: () => mockUseLocalSearchParams(),
}));

jest.mock('../../features/notes/use-notes', () => ({
  useNoteDetail: (noteId: string) => mockUseNoteDetail(noteId),
}));

jest.mock('../../components/ui/screen', () => ({
  Screen: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock('../../components/ui/section-card', () => ({
  SectionCard: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock('../../components/notes/note-card', () => ({
  NoteCard: () => null,
}));

import NoteScreen from '../../app/(tabs)/note/[noteId]';

describe('NoteScreen navigation context', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockPush.mockReset();
    mockUseLocalSearchParams.mockReturnValue({
      noteId: 'Notes/Ada.md',
      returnTo: '/(tabs)/chat/conv-1',
    });
    mockUseNoteDetail.mockReturnValue({
      data: {
        id: 'note-1',
        filePath: 'Notes/Ada.md',
        title: 'Ada',
        bodyMarkdown: 'Contenu',
        tags: [],
        frontmatter: {},
        backlinks: [],
        links: [],
      },
      isLoading: false,
      isRefetching: false,
      refetch: jest.fn(),
    });
  });

  it('renders a return button to the originating conversation and uses replace', () => {
    const tree = renderer.create(<NoteScreen />);

    act(() => {
      tree.root.findByProps({ testID: 'note-return-button' }).props.onPress();
    });

    expect(mockReplace).toHaveBeenCalledWith('/(tabs)/chat/conv-1');
  });
});